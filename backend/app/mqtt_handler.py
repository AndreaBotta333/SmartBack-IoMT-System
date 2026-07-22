"""MQTT ingestion, realtime state, alert publication and stream watchdog."""

import asyncio
import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import paho.mqtt.client as mqtt

from app.device_contract import NormalizedDeviceStatus, NormalizedPostureSample
from app.influx_manager import InfluxManager
from app.night_service import NightPositionEngine
from app.posture_service import PostureEngine


BroadcastCallback = Callable[[dict[str, Any]], Awaitable[None]]
DeviceSeenCallback = Callable[[str, str], None]
AssignmentProvider = Callable[[], list[dict[str, str]]]
SimulatedDeviceProvider = Callable[[], list[str]]
ActiveNightSimulationProvider = Callable[[], list[str]]
AlertCallback = Callable[[dict[str, Any]], None]


class SmartBackMqttHandler:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        posture_topic: str,
        device_topic: str,
        alert_topic: str,
        stale_seconds: float,
        posture_engine: PostureEngine,
        influx: InfluxManager,
        broadcast: BroadcastCallback,
        device_seen: DeviceSeenCallback | None = None,
        assignment_provider: AssignmentProvider | None = None,
        simulated_device_provider: SimulatedDeviceProvider | None = None,
        active_night_simulation_provider: ActiveNightSimulationProvider | None = None,
        night_engine: NightPositionEngine | None = None,
        alert_callback: AlertCallback | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.posture_topic = posture_topic
        self.device_topic = device_topic
        self.alert_topic = alert_topic
        self.stale_seconds = stale_seconds
        self.posture_engine = posture_engine
        self.influx = influx
        self.broadcast = broadcast
        self.device_seen = device_seen
        self.assignment_provider = assignment_provider
        self.simulated_device_provider = simulated_device_provider
        self.active_night_simulation_provider = active_night_simulation_provider
        self.night_engine = night_engine
        self.alert_callback = alert_callback

        self._lock = threading.RLock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._watchdog_task: asyncio.Task | None = None
        self._client: mqtt.Client | None = None
        self._latest_posture: dict[str, Any] | None = None
        self._latest_device: dict[str, Any] | None = None
        self._last_posture_alert: dict[str, str | None] = {}
        self._last_sample_monotonic: dict[str, float] = {}
        self._device_patient: dict[str, str] = {}
        self._monitoring_session: dict[str, str] = {}
        self._stale_alerted: set[str] = set()
        self._last_raw_device_seen: dict[str, float] = {}
        self._last_battery_alert: dict[str, str | None] = {}

    @property
    def latest_posture(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._latest_posture) if self._latest_posture else None

    @property
    def latest_device(self) -> dict[str, Any] | None:
        with self._lock:
            return dict(self._latest_device) if self._latest_device else None

    @property
    def connected(self) -> bool:
        return bool(self._client and self._client.is_connected())

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smartback-backend")
        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.reconnect_delay_set(min_delay=1, max_delay=10)
        client.connect_async(self.host, self.port, keepalive=60)
        client.loop_start()
        self._client = client
        self._watchdog_task = loop.create_task(self._monitor_data_stream())

    async def stop(self) -> None:
        if self._watchdog_task:
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    def calibrate(self, device_id: str) -> dict[str, float | str]:
        sample = self.latest_posture
        if sample is None or sample.get("device_id") != device_id:
            raise LookupError("No current sample is available for this device")
        return self.posture_engine.calibrate(device_id, sample)

    def calibrate_from_sample(
        self, device_id: str, sample: dict[str, Any]
    ) -> dict[str, float | str]:
        """Apply an immutable sample captured before a later confirmation."""
        if sample.get("device_id") != device_id:
            raise LookupError("The captured sample does not belong to this device")
        return self.posture_engine.calibrate(device_id, dict(sample))

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: Any,
        reason_code: Any,
        properties: Any,
    ) -> None:
        if reason_code == 0:
            client.subscribe(
                [
                    (self.posture_topic, 1),
                    (self.device_topic, 1),
                    ("unisadiem/smartshirt/+/+", 0),
                ]
            )
            if self.assignment_provider:
                for assignment in self.assignment_provider():
                    self.publish_device_assignment(
                        assignment["device_id"], assignment["patient_id"]
                    )
            if self.simulated_device_provider:
                for device_id in self.simulated_device_provider():
                    self.publish_simulated_device(device_id, active=True)
            if self.active_night_simulation_provider:
                for device_id in self.active_night_simulation_provider():
                    self.publish_simulation_scenario(device_id, "night-cycle")
            print(
                f"MQTT connected; subscribed to {self.posture_topic}, "
                f"{self.device_topic} and smart-shirt discovery",
                flush=True,
            )
        else:
            print(f"MQTT connection failed: {reason_code}", flush=True)

    def publish_device_assignment(
        self, device_id: str, patient_id: str | None
    ) -> None:
        if self._client is None:
            return
        with self._lock:
            if patient_id is None:
                self._device_patient.pop(device_id, None)
            else:
                self._device_patient[device_id] = patient_id
        payload = {
            "device_id": device_id,
            "patient_id": patient_id,
            "active": patient_id is not None,
            "updated_at": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        self._client.publish(
            f"smartback/config/device-assignments/{device_id}",
            json.dumps(payload),
            qos=1,
            retain=True,
        )

    def publish_simulated_device(self, device_id: str, *, active: bool) -> None:
        if self._client is None:
            return
        self._client.publish(
            f"smartback/config/simulated-devices/{device_id}",
            json.dumps({"device_id": device_id, "active": active}),
            qos=1,
            retain=True,
        )

    def publish_simulation_scenario(self, device_id: str, scenario: str) -> None:
        """Switch only the development emulator; physical shirts ignore this topic."""
        if self._client is None:
            return
        self._client.publish(
            f"smartback/config/simulation-scenarios/{device_id}",
            json.dumps({"device_id": device_id, "scenario": scenario}),
            qos=1,
            retain=True,
        )

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        try:
            topic_parts = message.topic.split("/")
            if (
                len(topic_parts) >= 4
                and topic_parts[0] == "unisadiem"
                and topic_parts[1] == "smartshirt"
            ):
                # Discovery is intentionally independent from posture ingestion:
                # even packets we do not process (for example ECG and strain
                # gauges) prove that the physical shirt is online. Throttle the
                # durable update because those streams can be very frequent.
                device_id = topic_parts[2].strip()
                now = time.monotonic()
                last_seen = self._last_raw_device_seen.get(device_id, 0.0)
                if device_id and self.device_seen and now - last_seen >= 5.0:
                    self._last_raw_device_seen[device_id] = now
                    self.device_seen(device_id, "measured")
                return

            raw_payload = json.loads(message.payload.decode("utf-8"))
            if message.topic == self.posture_topic:
                payload = NormalizedPostureSample.model_validate(raw_payload).model_dump()
                if self.device_seen:
                    self.device_seen(str(payload["device_id"]), str(payload["quality"]))
                self._mark_stream_active(client, payload)
                night_sample = (
                    self.night_engine.process(payload)
                    if self.night_engine is not None
                    else None
                )
                if night_sample is not None:
                    # Daytime posture and night orientation are mutually exclusive.
                    # Stop feeding live/day history while the patient selected night mode.
                    with self._lock:
                        self._latest_posture = None
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            self.broadcast({"mode": "night", **night_sample}), self._loop
                        )
                else:
                    processed = self.posture_engine.process(payload)
                    with self._lock:
                        processed["session_id"] = self._monitoring_session[
                            str(payload["device_id"])
                        ]
                    self.influx.persist_posture(processed)
                    self._publish_posture_transition(client, processed)
                    with self._lock:
                        self._latest_posture = processed
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(self.broadcast(processed), self._loop)
            elif message.topic == self.device_topic:
                payload = NormalizedDeviceStatus.model_validate(raw_payload).model_dump()
                if self.device_seen:
                    self.device_seen(str(payload["device_id"]), str(payload["quality"]))
                with self._lock:
                    self._latest_device = payload
                self._publish_battery_transition(client, payload)
        except Exception as exc:
            print(f"Cannot process MQTT message from {message.topic}: {exc}", flush=True)

    def _mark_stream_active(self, client: mqtt.Client, payload: dict[str, Any]) -> None:
        device_id = str(payload["device_id"])
        patient_id = str(payload["patient_id"])
        recovery_silence: float | None = None
        with self._lock:
            now = time.monotonic()
            previous_seen = self._last_sample_monotonic.get(device_id, now)
            if device_id not in self._monitoring_session or device_id in self._stale_alerted:
                self._monitoring_session[device_id] = self._new_session_id()
            self._last_sample_monotonic[device_id] = now
            self._device_patient[device_id] = patient_id
            if device_id in self._stale_alerted:
                self._stale_alerted.discard(device_id)
                recovery_silence = now - previous_seen
        if recovery_silence is not None:
            self._publish_stream_alert(
                client,
                device_id=device_id,
                patient_id=patient_id,
                active=False,
                silent_seconds=recovery_silence,
            )

    @staticmethod
    def _new_session_id() -> str:
        """Return a sortable identifier representing the session start instant."""
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def _publish_posture_transition(
        self,
        client: mqtt.Client,
        processed: dict[str, Any],
    ) -> None:
        device_id = str(processed["device_id"])
        current_alert = processed["alert"]
        previous_alert = self._last_posture_alert.get(device_id)
        if current_alert == previous_alert:
            return
        episode_started = current_alert is not None and previous_alert is None
        payload = {
            "schema_version": 1,
            "timestamp": int(processed["timestamp"]),
            "device_id": device_id,
            "patient_id": processed["patient_id"],
            "category": "posture",
            "severity": "critical" if current_alert == "POSTURE_MARKED_DEVIATION" else "warning",
            "code": current_alert or previous_alert or "POSTURE_OK",
            "message": (
                "Superata la soglia di inclinazione elevata"
                if current_alert == "POSTURE_MARKED_DEVIATION"
                else "Inclinazione mantenuta oltre il tempo consentito"
                if current_alert == "POSTURE_PROLONGED_DEVIATION"
                else "Postura tornata entro i limiti"
            ),
            "active": current_alert is not None,
            "episode_started": episode_started,
            "deviation_deg": processed["deviation_deg"],
            "pitch_deviation_deg": processed["pitch_deviation_deg"],
            "roll_deviation_deg": processed["roll_deviation_deg"],
            "dominant_axis": processed["dominant_axis"],
            "duration_seconds": processed["deviation_duration_seconds"],
            "session_id": self._monitoring_session.get(device_id),
        }
        self._publish_alert(client, payload)
        self._last_posture_alert[device_id] = current_alert

    def _publish_battery_transition(self, client: mqtt.Client, payload: dict[str, Any]) -> None:
        device_id = str(payload["device_id"])
        charge = payload.get("state_of_charge")
        patient_id = self._device_patient.get(device_id)
        if charge is None or not patient_id:
            return
        charge = float(charge)
        code = "BATTERY_CRITICAL" if charge <= 10 else "BATTERY_LOW" if charge <= 20 else None
        previous = self._last_battery_alert.get(device_id)
        if code == previous:
            return
        self._last_battery_alert[device_id] = code
        if code is None:
            return
        self._publish_alert(client, {
            "schema_version": 1,
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "device_id": device_id,
            "patient_id": patient_id,
            "category": "battery",
            "severity": "critical" if code == "BATTERY_CRITICAL" else "warning",
            "code": code,
            "message": f"Batteria residua {charge:.0f}%",
            "active": True,
            "state_of_charge": charge,
            "session_id": self._monitoring_session.get(device_id),
        })

    def _publish_alert(self, client: mqtt.Client, payload: dict[str, Any]) -> None:
        client.publish(self.alert_topic, json.dumps(payload), qos=1)
        alert_callback = getattr(self, "alert_callback", None)
        if alert_callback:
            alert_callback(dict(payload))

    def _publish_stream_alert(
        self,
        client: mqtt.Client,
        *,
        device_id: str,
        patient_id: str,
        active: bool,
        silent_seconds: float,
    ) -> None:
        payload = {
            "schema_version": 1,
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "device_id": device_id,
            "patient_id": patient_id,
            "category": "connectivity",
            "severity": "critical" if active else "info",
            "code": "DATA_STREAM_STALE" if active else "DATA_STREAM_RESTORED",
            "message": (
                f"La maglia non trasmette dati da {silent_seconds:.1f} secondi"
                if active
                else "La maglia ha ripreso a trasmettere"
            ),
            "active": active,
            "silent_seconds": round(silent_seconds, 1),
            "session_id": self._monitoring_session.get(device_id),
        }
        self._publish_alert(client, payload)

    async def _monitor_data_stream(self) -> None:
        while True:
            await asyncio.sleep(1)
            client = self._client
            if client is None or not client.is_connected():
                continue
            now = time.monotonic()
            stale: list[tuple[str, str, float]] = []
            with self._lock:
                for device_id, last_seen in self._last_sample_monotonic.items():
                    silent_seconds = now - last_seen
                    if silent_seconds < self.stale_seconds or device_id in self._stale_alerted:
                        continue
                    self._stale_alerted.add(device_id)
                    stale.append((device_id, self._device_patient[device_id], silent_seconds))
            for device_id, patient_id, silent_seconds in stale:
                self._publish_stream_alert(
                    client,
                    device_id=device_id,
                    patient_id=patient_id,
                    active=True,
                    silent_seconds=silent_seconds,
                )

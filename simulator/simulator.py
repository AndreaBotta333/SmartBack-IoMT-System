"""Deterministic MQTT emulator for the immutable ESP32 smart-shirt gateway.

The emulator starts *after* the BLE decoding boundary: it publishes the same
topics and JSON produced by ``datastream.py`` on the ESP32. Consequently every
downstream component (Mosquitto, Node-RED, FastAPI, InfluxDB and Grafana) uses
the exact same path as with the physical shirt.
"""

from __future__ import annotations

import json
import math
import os
import random
import signal
import threading
import time
from dataclasses import dataclass
from typing import Any


MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "tshirt-sim-001")
SAMPLING_FREQUENCY_HZ = int(os.getenv("SAMPLING_FREQUENCY_HZ", "25"))
SAMPLES_PER_PACKET = int(os.getenv("SAMPLES_PER_PACKET", "16"))
PACKET_INTERVAL_SECONDS = float(
    os.getenv(
        "PACKET_INTERVAL_SECONDS",
        str(SAMPLES_PER_PACKET / SAMPLING_FREQUENCY_HZ),
    )
)
BATTERY_INTERVAL_SECONDS = float(os.getenv("BATTERY_INTERVAL_SECONDS", "30"))
SYSTEM_INFO_INTERVAL_SECONDS = float(os.getenv("SYSTEM_INFO_INTERVAL_SECONDS", "60"))
INITIAL_BATTERY_PERCENT = int(os.getenv("INITIAL_BATTERY_PERCENT", "96"))
SCENARIO_NAME = os.getenv("SIMULATION_SCENARIO", "day-cycle")
RANDOM_SEED = int(os.getenv("SIMULATION_SEED", "20260717"))
GRAVITY_COUNTS = int(os.getenv("GRAVITY_COUNTS", "16384"))
NOISE_STD_COUNTS = float(os.getenv("NOISE_STD_COUNTS", "45"))
DROP_EVERY_N_PACKETS = int(os.getenv("DROP_EVERY_N_PACKETS", "0"))
REPORT_DATALOSS_ON_DROP = os.getenv("REPORT_DATALOSS_ON_DROP", "true").lower() in {
    "1",
    "true",
    "yes",
}


@dataclass(frozen=True)
class Pose:
    name: str
    pitch_deg: float
    roll_deg: float


DAY_CYCLE = (
    (12.0, Pose("neutral", 0.0, 0.0)),
    (12.0, Pose("forward", 15.0, 0.0)),
    (8.0, Pose("neutral", 0.0, 0.0)),
    (12.0, Pose("backward", -15.0, 0.0)),
    (8.0, Pose("neutral", 0.0, 0.0)),
    (12.0, Pose("right", 0.0, 15.0)),
    (8.0, Pose("neutral", 0.0, 0.0)),
    (12.0, Pose("left", 0.0, -15.0)),
    (12.0, Pose("marked-forward", 25.0, 0.0)),
)


def pose_at(elapsed: float, scenario_name: str = SCENARIO_NAME) -> Pose:
    """Return a reproducible posture for the selected scenario."""
    if scenario_name == "neutral":
        return Pose("neutral", 0.0, 0.0)
    if scenario_name == "manual":
        return Pose(
            "manual",
            float(os.getenv("SIMULATOR_PITCH_DEG", "0")),
            float(os.getenv("SIMULATOR_ROLL_DEG", "0")),
        )
    if scenario_name != "day-cycle":
        raise ValueError(f"Unsupported SIMULATION_SCENARIO={scenario_name!r}")

    position = elapsed % sum(duration for duration, _ in DAY_CYCLE)
    for duration, pose in DAY_CYCLE:
        if position < duration:
            return pose
        position -= duration
    return DAY_CYCLE[-1][1]


def gravity_vector(pitch_deg: float, roll_deg: float) -> tuple[float, float, float]:
    """Generate axes matching the real shirt mounting used by the backend.

    Y is vertical, Z preserves forward/backward direction and X preserves the
    lateral direction. This is the inverse of the backend pitch/roll formulas.
    """
    pitch = math.radians(pitch_deg)
    roll = math.radians(roll_deg)
    x = math.sin(roll) * math.cos(pitch)
    y = math.cos(roll) * math.cos(pitch)
    z = -math.sin(pitch)
    return x, y, z


def accelerometer_samples(
    pose: Pose, rng: random.Random, count: int = SAMPLES_PER_PACKET
) -> list[dict[str, int]]:
    x, y, z = gravity_vector(pose.pitch_deg, pose.roll_deg)
    def int16(value: float) -> int:
        return max(-32768, min(32767, round(value)))

    return [
        {
            "x": int16(x * GRAVITY_COUNTS + rng.gauss(0, NOISE_STD_COUNTS)),
            "y": int16(y * GRAVITY_COUNTS + rng.gauss(0, NOISE_STD_COUNTS)),
            "z": int16(z * GRAVITY_COUNTS + rng.gauss(0, NOISE_STD_COUNTS)),
        }
        for _ in range(count)
    ]


def accgyro_payload(
    *, elapsed_ms: int, sample_number: int, pose: Pose, rng: random.Random
) -> dict:
    """Match ``AccGyroWaveform.to_json`` from the ESP32 exactly."""
    return {
        "type": "accgyro",
        "timestamp": elapsed_ms & 0xFFFFFFFF,
        "samplenum": sample_number & 0xFFFFFFFF,
        "sampling_frequency": SAMPLING_FREQUENCY_HZ,
        "orientation": 0,
        "samples": accelerometer_samples(pose, rng),
    }


def battery_payload(state_of_charge: int) -> dict:
    """Match ``BatteryInfoPacketHandler.to_json`` from the ESP32."""
    remaining = round(2400 * state_of_charge / 100)
    return {
        "type": "battery",
        "charging": 0,
        "temperature": 250,
        "voltage": round(3300 + 9 * state_of_charge),
        "full_actual_capacity": 2400,
        "nominal_capacity": 2400,
        "remaining_capacity": remaining,
        "average_current": 35,
        "state_of_charge": state_of_charge,
    }


def dataloss_payload(missing_packets: int = 1) -> dict:
    """Match ``DataLossPacketHandler.to_json`` from the ESP32."""
    return {"type": "dataloss", "value": max(0, min(255, missing_packets))}


def system_info_payload(elapsed_ms: int) -> dict:
    """Match the enabled fields emitted by ``SystemInfoPacketHandler``."""
    return {
        "type": "system_info",
        "timestamp": elapsed_ms & 0xFFFFFFFF,
        "sampleperiod": round(1000 / SAMPLING_FREQUENCY_HZ),
        "demo": 0,
        "accelerometer": 1,
        "battery": 1,
        "mems_mode": 1,
        "led_mode": 0,
        "pressure": 0,
        "temperature": 0,
        "ecg": 0,
        "bio": 0,
        "r2r": 0,
        "orientation": 0,
        "ecg_frequency": 0,
    }


def mqtt_module():
    """Load the transport only when the emulator is actually started."""
    import paho.mqtt.client as mqtt

    return mqtt


def publish(client: Any, device_id: str, packet_id: str, payload: dict) -> None:
    # umqtt.simple.publish() on the ESP uses QoS 0 and retain=False by default.
    info = client.publish(
        f"unisadiem/smartshirt/{device_id}/{packet_id}",
        json.dumps(payload, separators=(",", ":")),
        qos=0,
        retain=False,
    )
    if info.rc != mqtt_module().MQTT_ERR_SUCCESS:
        raise OSError(f"MQTT publish failed with rc={info.rc}")


def connect(configured_devices: set[str], devices_lock: threading.RLock) -> Any:
    mqtt = mqtt_module()
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id="smartshirt-emulator-registry",
    )
    def on_connect(connected, _userdata, _flags, reason_code, _properties):
        if reason_code == 0:
            connected.subscribe("smartback/config/simulated-devices/+", qos=1)

    def on_message(_client, _userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            device_id = str(payload["device_id"])
            with devices_lock:
                if payload.get("active"):
                    configured_devices.add(device_id)
                else:
                    configured_devices.discard(device_id)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"Configurazione simulatore non valida: {exc}", flush=True)

    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            return client
        except OSError as exc:
            print(f"MQTT non disponibile ({exc}); nuovo tentativo", flush=True)
            time.sleep(2)


def main() -> None:
    if SAMPLING_FREQUENCY_HZ <= 0 or SAMPLES_PER_PACKET <= 0:
        raise ValueError("Sampling frequency and samples per packet must be positive")
    if PACKET_INTERVAL_SECONDS <= 0:
        raise ValueError("PACKET_INTERVAL_SECONDS must be positive")
    if DROP_EVERY_N_PACKETS < 0:
        raise ValueError("DROP_EVERY_N_PACKETS cannot be negative")

    stop_requested = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    configured_devices = {DEVICE_ID} if DEVICE_ID else set()
    devices_lock = threading.RLock()
    client = connect(configured_devices, devices_lock)
    started = time.monotonic()
    runtimes: dict[str, dict[str, Any]] = {}

    print(
        f"Emulatore multi-maglia: scenario={SCENARIO_NAME}, "
        f"{SAMPLES_PER_PACKET} campioni ogni {PACKET_INTERVAL_SECONDS:.3f}s",
        flush=True,
    )

    try:
        while not stop_requested:
            now = time.monotonic()
            elapsed = now - started
            elapsed_ms = int(elapsed * 1000)
            with devices_lock:
                active_devices = set(configured_devices)
            for removed in set(runtimes) - active_devices:
                del runtimes[removed]
                print(f"Emulatore {removed} disattivato", flush=True)
            for device_id in sorted(active_devices):
                runtime = runtimes.setdefault(device_id, {
                    "next_packet": now,
                    "next_battery": now,
                    "next_system_info": now,
                    "sample_number": 0,
                    "battery": INITIAL_BATTERY_PERCENT,
                    "rng": random.Random(RANDOM_SEED + sum(map(ord, device_id))),
                })
                if now >= runtime["next_system_info"]:
                    publish(client, device_id, "SYSTEM_INFO", system_info_payload(elapsed_ms))
                    runtime["next_system_info"] = now + SYSTEM_INFO_INTERVAL_SECONDS
                if now >= runtime["next_battery"]:
                    publish(client, device_id, "BATTERY_INFO", battery_payload(runtime["battery"]))
                    runtime["battery"] = max(5, runtime["battery"] - 1)
                    runtime["next_battery"] = now + BATTERY_INTERVAL_SECONDS
                if now < runtime["next_packet"]:
                    continue
                pose = pose_at(elapsed + len(runtimes) * 3)
                sample_number = runtime["sample_number"]
                drop_packet = (
                    DROP_EVERY_N_PACKETS > 0
                    and sample_number > 0
                    and sample_number % DROP_EVERY_N_PACKETS == 0
                )
                if drop_packet:
                    if REPORT_DATALOSS_ON_DROP:
                        publish(client, device_id, "DATALOSS", dataloss_payload())
                    print(f"{device_id} ACC_GYRO #{sample_number} perso (test)", flush=True)
                else:
                    publish(
                        client,
                        device_id,
                        "ACC_GYRO",
                        accgyro_payload(
                            elapsed_ms=elapsed_ms,
                            sample_number=sample_number,
                            pose=pose,
                            rng=runtime["rng"],
                        ),
                    )
                    print(
                        f"{device_id} ACC_GYRO #{sample_number} {pose.name} "
                        f"pitch={pose.pitch_deg:+.1f} roll={pose.roll_deg:+.1f}",
                        flush=True,
                    )
                # Nella telemetria osservata ``samplenum`` e progressivo per
                # pacchetto, mentre ``samples`` contiene i 16 valori MEMS.
                runtime["sample_number"] += 1
                runtime["next_packet"] += PACKET_INTERVAL_SECONDS
                if runtime["next_packet"] < now:
                    runtime["next_packet"] = now + PACKET_INTERVAL_SECONDS

            time.sleep(0.02)
    finally:
        client.loop_stop()
        client.disconnect()
        print("Emulatore arrestato", flush=True)


if __name__ == "__main__":
    main()

"""Avvio e arresto coordinato delle infrastrutture SmartBack."""

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable

from app.infrastructure.database import init_database
from app.domain.night import NightPositionEngine
from app.domain.posture import PostureEngine
from app.infrastructure.influx import InfluxManager
from app.infrastructure.mqtt import SmartBackMqttHandler


@dataclass(frozen=True)
class RuntimeConfig:
    auth_db_path: str
    influx_url: str
    influx_token: str
    influx_org: str
    influx_bucket: str
    mqtt_host: str
    mqtt_port: int
    posture_topic: str
    device_topic: str
    alert_topic: str
    stale_seconds: float
    posture_ema_alpha: float
    posture_hysteresis_deg: float


@dataclass(frozen=True)
class RuntimeComponents:
    database: sqlite3.Connection
    influx: InfluxManager
    posture_engine: PostureEngine
    night_engine: NightPositionEngine
    mqtt: SmartBackMqttHandler


def create_runtime_lifespan(
    config: RuntimeConfig,
    *,
    bind_database: Callable[[sqlite3.Connection], None],
    bind_components: Callable[[RuntimeComponents], None],
    ensure_admin: Callable[[], None],
    threshold_provider: Callable,
    calibration_provider: Callable,
    night_session_provider: Callable,
    night_summary_updater: Callable,
    broadcast: Callable,
    device_seen: Callable,
    assignment_provider: Callable,
    simulated_device_provider: Callable,
    active_night_simulation_provider: Callable,
    active_night_sessions_provider: Callable,
    alert_dispatcher: Callable,
):
    """Costruisce il lifespan FastAPI senza dipendere dal modulo `main`."""

    @asynccontextmanager
    async def lifespan(_app):
        loop = asyncio.get_running_loop()
        database = init_database(config.auth_db_path)
        bind_database(database)
        ensure_admin()

        influx = InfluxManager(
            url=config.influx_url,
            token=config.influx_token,
            org=config.influx_org,
            bucket=config.influx_bucket,
        )
        active_sessions = active_night_sessions_provider()
        for session in active_sessions:
            try:
                influx.persist_night_session_state(
                    patient_code=str(session["patient_code"]),
                    session_id=str(session["id"]),
                    device_id=str(session["device_id"]),
                    active=True,
                )
            except Exception as error:
                print(
                    "Unable to reconcile night session "
                    f"{session['id']}: {error}"
                )

        posture_engine = PostureEngine(
            threshold_provider,
            ema_alpha=config.posture_ema_alpha,
            hysteresis_deg=config.posture_hysteresis_deg,
            calibration_provider=calibration_provider,
        )
        night_engine = NightPositionEngine(
            session_provider=night_session_provider,
            summary_updater=night_summary_updater,
            persister=influx.persist_night_position,
            gap_seconds=config.stale_seconds,
        )
        mqtt = SmartBackMqttHandler(
            host=config.mqtt_host,
            port=config.mqtt_port,
            posture_topic=config.posture_topic,
            device_topic=config.device_topic,
            alert_topic=config.alert_topic,
            stale_seconds=config.stale_seconds,
            posture_engine=posture_engine,
            influx=influx,
            broadcast=broadcast,
            device_seen=device_seen,
            assignment_provider=assignment_provider,
            simulated_device_provider=simulated_device_provider,
            active_night_simulation_provider=(
                active_night_simulation_provider
            ),
            night_engine=night_engine,
            alert_callback=lambda payload: asyncio.run_coroutine_threadsafe(
                alert_dispatcher(payload),
                loop,
            ),
        )
        components = RuntimeComponents(
            database=database,
            influx=influx,
            posture_engine=posture_engine,
            night_engine=night_engine,
            mqtt=mqtt,
        )
        bind_components(components)
        mqtt.start(loop)
        try:
            yield
        finally:
            await mqtt.stop()
            influx.close()
            database.close()

    return lifespan

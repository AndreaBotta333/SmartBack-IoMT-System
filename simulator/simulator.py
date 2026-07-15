"""HOWDY-like data source used until the physical smart shirt is available.

It intentionally publishes sensor-shaped raw data. Posture calculations and alert
logic remain server-side, exactly as they will when this source is replaced by the
ESP32 BLE-to-MQTT gateway.
"""

import json
import math
import os
import random
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DEVICE_ID = os.getenv("DEVICE_ID", "howdy-sim-001")
PATIENT_ID = os.getenv("PATIENT_ID", "patient-demo-001")
INTERVAL = float(os.getenv("PUBLISH_INTERVAL_SECONDS", "1"))


def connect() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"sim-{DEVICE_ID}")
    while True:
        try:
            client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
            client.loop_start()
            return client
        except OSError as exc:
            print(f"MQTT unavailable ({exc}); retrying", flush=True)
            time.sleep(2)


def scenario(elapsed: float) -> tuple[str, float, float]:
    """Return a repeating demo state, forward tilt and lateral tilt in degrees."""
    phase = elapsed % 180
    if phase < 35:
        return "neutral", 2.0 + math.sin(elapsed / 4), math.sin(elapsed / 7)
    if phase < 75:
        return "moderate_forward", 13.0 + math.sin(elapsed / 3), 1.0
    if phase < 105:
        return "neutral", 3.0, math.sin(elapsed / 5)
    if phase < 145:
        return "marked_forward", 24.0 + 2 * math.sin(elapsed / 4), 2.0
    return "moving", 6.0 + 8 * math.sin(elapsed * 1.7), 5 * math.sin(elapsed * 1.2)


def gravity_vector(forward_deg: float, lateral_deg: float) -> tuple[float, float, float]:
    pitch = math.radians(forward_deg)
    roll = math.radians(lateral_deg)
    x = math.sin(roll) * math.cos(pitch)
    y = math.sin(pitch)
    z = math.cos(roll) * math.cos(pitch)
    noise = lambda: random.gauss(0, 0.008)
    return x + noise(), y + noise(), z + noise()


def main() -> None:
    client = connect()
    started = time.monotonic()
    sequence = 0
    battery = 96.0

    while True:
        elapsed = time.monotonic() - started
        state, forward, lateral = scenario(elapsed)
        x, y, z = gravity_vector(forward, lateral)
        now = datetime.now(timezone.utc)
        timestamp_ms = int(now.timestamp() * 1000)
        sequence += 1

        accelerometer = {
            "schema_version": 1,
            "device_id": DEVICE_ID,
            "patient_id": PATIENT_ID,
            "timestamp": timestamp_ms,
            "sequence": sequence,
            "type": "accgyro",
            "sampling_frequency": 1,
            "samples": [{"x": round(x, 5), "y": round(y, 5), "z": round(z, 5)}],
            "quality": "simulated",
            "simulation_state": state,
        }
        client.publish("smartback/raw/accgyro", json.dumps(accelerometer), qos=1)

        if sequence == 1 or sequence % 10 == 0:
            battery = max(5.0, battery - 0.05)
            device = {
                "schema_version": 1,
                "device_id": DEVICE_ID,
                "patient_id": PATIENT_ID,
                "timestamp": timestamp_ms,
                "type": "battery",
                "state_of_charge": round(battery, 1),
                "charging": False,
                "quality": "simulated",
            }
            client.publish("smartback/raw/battery", json.dumps(device), qos=1, retain=True)

        print(f"#{sequence} {state} raw=({x:.3f},{y:.3f},{z:.3f})", flush=True)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()

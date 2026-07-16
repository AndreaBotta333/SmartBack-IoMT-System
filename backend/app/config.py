"""Centralized runtime configuration for the SmartBack backend."""

import os


MQTT_HOST = os.getenv("MQTT_HOST", "mosquitto")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
POSTURE_TOPIC = os.getenv("MQTT_POSTURE_TOPIC", "smartback/normalized/posture")
DEVICE_TOPIC = os.getenv("MQTT_DEVICE_TOPIC", "smartback/normalized/device")
ALERT_TOPIC = os.getenv("MQTT_ALERT_TOPIC", "smartback/alerts/posture")

INFLUX_URL = os.getenv("INFLUXDB_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUXDB_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUXDB_ORG", "smartback")
INFLUX_BUCKET = os.getenv("INFLUXDB_BUCKET", "posture")

# Demonstration defaults, not clinical thresholds. They will become configurable.
MODERATE_DEVIATION_DEG = float(os.getenv("MODERATE_DEVIATION_DEG", "10"))
MARKED_DEVIATION_DEG = float(os.getenv("MARKED_DEVIATION_DEG", "20"))
PERSISTENCE_SECONDS = float(os.getenv("PERSISTENCE_SECONDS", "5"))

AUTH_DB_PATH = os.getenv("AUTH_DB_PATH", "/app/data/smartback.db")
MEDICAL_REGISTRATION_CODE = os.getenv("MEDICAL_REGISTRATION_CODE", "SMARTBACK-MED-2026")

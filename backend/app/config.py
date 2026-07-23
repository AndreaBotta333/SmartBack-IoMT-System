"""Configurazione runtime centralizzata del backend SmartBack."""

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

# Valori dimostrativi predefiniti, non soglie cliniche; saranno configurabili.
MODERATE_DEVIATION_DEG = float(os.getenv("MODERATE_DEVIATION_DEG", "10"))
MARKED_DEVIATION_DEG = float(os.getenv("MARKED_DEVIATION_DEG", "20"))
MODERATE_ROLL_DEG = float(os.getenv("MODERATE_ROLL_DEG", "10"))
MARKED_ROLL_DEG = float(os.getenv("MARKED_ROLL_DEG", "20"))
PERSISTENCE_SECONDS = float(os.getenv("PERSISTENCE_SECONDS", "5"))
POSTURE_EMA_ALPHA = float(os.getenv("POSTURE_EMA_ALPHA", "0.5"))
POSTURE_HYSTERESIS_DEG = float(os.getenv("POSTURE_HYSTERESIS_DEG", "2"))
DATA_STALE_SECONDS = float(os.getenv("DATA_STALE_SECONDS", "10"))

AUTH_DB_PATH = os.getenv("AUTH_DB_PATH", "/app/data/smartback.db")
MEDICAL_REGISTRATION_CODE = os.getenv("MEDICAL_REGISTRATION_CODE", "SMARTBACK-MED-2026")
GRAFANA_ADMIN_USER = os.getenv("GRAFANA_ADMIN_USER", "admin")
GRAFANA_ADMIN_PASSWORD = os.getenv(
    "GRAFANA_ADMIN_PASSWORD", "smartback-dev-password"
)

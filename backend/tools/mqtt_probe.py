"""Print SmartBack MQTT traffic to verify a simulator or physical gateway."""

import json
import os
import signal

import paho.mqtt.client as mqtt


HOST = os.getenv("MQTT_HOST", "mosquitto")
PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("MQTT_PROBE_TOPIC", "smartback/#")


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code != 0:
        raise RuntimeError(f"MQTT connection failed: {reason_code}")
    print(f"Connected to {HOST}:{PORT}; listening on {TOPIC}", flush=True)
    client.subscribe(TOPIC, qos=1)


def on_message(client, userdata, message):
    text = message.payload.decode("utf-8", errors="replace")
    try:
        text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        pass
    print(f"\n[{message.topic}] retain={message.retain} qos={message.qos}\n{text}", flush=True)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="smartback-probe")
client.on_connect = on_connect
client.on_message = on_message
client.connect(HOST, PORT, keepalive=60)
signal.signal(signal.SIGINT, lambda *_: client.disconnect())
client.loop_forever()

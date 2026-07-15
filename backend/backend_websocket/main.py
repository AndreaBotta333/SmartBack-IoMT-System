import asyncio
import math
import random
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.websocket("/ws/wearable")
async def wearable_stream(websocket: WebSocket):
    await websocket.accept()

    try:
        t = 0
        while True:
            heart_rate = 75 + 12 * math.sin(t / 8) + random.uniform(-3, 3)
            spo2 = 97 + random.uniform(-0.5, 0.5)
            steps_per_min = max(0, 90 + 30 * math.sin(t / 13) + random.uniform(-10, 10))

            await websocket.send_json({
                "timestamp": int(time.time() * 1000),
                "heartRate": round(heart_rate, 1),
                "spo2": round(spo2, 1),
                "stepsPerMin": round(steps_per_min, 1)
            })

            t += 1
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        print("Client disconnected")
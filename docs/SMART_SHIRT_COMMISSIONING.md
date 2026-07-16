# Collegamento della smart shirt: checklist

## Prima del test

1. Copiare `.env.example` in `.env` e scegliere `DEVICE_ID` e `PATIENT_ID`.
2. Avviare lo stack reale senza simulatore:

   ```bash
   docker compose up -d --build
   ```

3. Verificare `http://localhost:8000/health`, Node-RED su porta `1880` e
   InfluxDB su porta `8086`.
4. Aprire un osservatore MQTT:

   ```bash
   docker compose exec backend python tools/mqtt_probe.py
   ```

## Durante il primo collegamento

Il gateway e l'ESP32 MicroPython gia disponibile. I suoi file sono considerati
un contratto non modificabile: il server deve adattarsi ai topic e ai payload
che pubblica.

Configurazione imposta dall'ESP32:

```text
Wi-Fi: OpenWrt
Broker: 192.168.2.51:1883
Base topic: unisadiem/smartshirt/tshirt002
```

Il computer che esegue Docker deve quindi essere raggiungibile dall'ESP32
all'indirizzo `192.168.2.51`. Mosquitto espone gia la porta `1883` sulla LAN e
accetta il client senza credenziali, come richiesto dal firmware attuale.

Node-RED ascolta:

```text
unisadiem/smartshirt/+/#
```

Esempio reale accelerometro:

```json
{
  "type": "accgyro",
  "timestamp": 123456,
  "samplenum": 16,
  "sampling_frequency": 25,
  "orientation": 0,
  "samples": [
    {"x": 120, "y": -30, "z": 16200}
  ]
}
```

Il pacchetto effettivo contiene 16 campioni. Node-RED calcola il vettore medio,
lo normalizza e pubblica il risultato su `smartback/normalized/posture`. Il
timestamp usato dal backend e quello di ricezione del server; il timestamp
originario della maglia viene conservato come `source_timestamp`.

`BATTERY_INFO` viene convertito in `smartback/normalized/device`. Tutti gli
altri tipi (`ECG`, `R2R`, `BREATH_WAVEFORM`, `TEMPERATURE`, ecc.) vengono
comunque ricevuti, archiviati in InfluxDB nella measurement `shirt_raw` e
ripubblicati su:

```text
smartback/shirt/raw/<device>/<tipo>
```

L'associazione con il paziente non e presente nei messaggi ESP32. Va impostata
in `.env`:

```env
SMARTSHIRT_PATIENT_ID=patient-demo-001
```

## Controlli di accettazione

- Il probe mostra prima `unisadiem/smartshirt/tshirt002/...`, poi il mirror raw
  e, per accelerometro/batteria, il topic normalizzato.
- `/api/v1/posture/latest` restituisce il device fisico e `quality=measured`.
- `/api/v1/device/latest` mostra batteria e timestamp plausibili.
- Il WebSocket `/ws/wearable` riceve campioni continui.
- InfluxDB contiene `raw_accelerometer`, `device_status` e `posture`.
- Scollegamento e riconnessione non richiedono il riavvio dello stack.
- La calibrazione viene eseguita con il soggetto in posa neutra tramite
  `POST /api/v1/devices/{device_id}/calibration`.

## Dove osservare i dati

- **Node-RED** (`http://localhost:1880`): nella sidebar Debug. I nodi
  `DEBUG 1`-`DEBUG 4` mostrano rispettivamente MQTT originale, JSON,
  postura normalizzata e device normalizzato. Sono disattivati inizialmente
  per evitare che ECG e stream veloci saturino l'editor; abilitarli uno alla
  volta dal pulsante del nodo.
- **FastAPI** (`http://localhost:8000/docs`):
  `/api/v1/posture/latest`, `/api/v1/device/latest` e `/health`.
- **Grafana** (`http://localhost:3000`): dashboard
  `SmartBack - Monitoraggio posturale`, aggiornata ogni 5 secondi.
- **App**: riceve in tempo reale postura, deviazione e stato attraverso
  `/ws/wearable`; recupera la batteria tramite REST.

## Alert

Node-RED genera:

- `BATTERY_LOW` sotto o uguale al 20%;
- `BATTERY_CRITICAL` sotto o uguale al 10%;
- `BATTERY_RECOVERED` quando il livello torna sopra il 20%;
- `DATA_LOSS` quando la maglia pubblica un pacchetto `DATALOSS`.

FastAPI genera gli alert posturali solo dopo il tempo di persistenza configurato:

- `POSTURE_PROLONGED_DEVIATION`;
- `POSTURE_MARKED_DEVIATION`;
- evento con `active=false` quando la postura rientra.

Gli alert transitano su `smartback/alerts/device` e
`smartback/alerts/posture`, vengono mostrati dal nodo
`DEBUG ALERT ATTIVI/RISOLTI` e salvati nella measurement InfluxDB `alerts`.

Per tornare al simulatore, avviare esplicitamente il profilo:

```bash
docker compose --profile simulation up -d --build simulator
```

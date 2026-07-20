# Collegamento della smart shirt: checklist

## Prima del test

1. Copiare `.env.example` in `.env` e scegliere `DEVICE_ID` e `PATIENT_ID`.
2. Avviare lo stack reale senza simulatore:

   ```bash
   docker compose up -d --build
   ```

   Se il simulatore era stato usato in precedenza, fermarlo esplicitamente:

   ```bash
   docker compose stop simulator
   ```

   Il servizio usa `restart: "no"`, quindi non riparte automaticamente al
   successivo avvio di Docker.

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

`BATTERY_INFO` viene convertito in `smartback/normalized/device`. Node-RED
conserva e archivia soltanto:

- `ACC_GYRO`;
- `BATTERY_INFO`;
- `DATALOSS`;
- `SYSTEM_INFO`.

ECG, R2R, respirazione, temperatura, strain gauges e diagnostica non necessaria
vengono scartati all'ingresso. Accelerometro e orientamento restano disponibili
anche per la futura stima del tempo trascorso seduti. `BABY_ORIENTATION` viene
scartato perché nelle prove è rimasto costante e duplica il campo orientation
già presente in `ACC_GYRO`.

I pacchetti conservati vengono ripubblicati su:

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
- La calibrazione viene eseguita con il soggetto in posa neutra dal pulsante
  **Fissa calibrazione** di Grafana oppure tramite la chiamata autenticata
  `POST /api/v1/devices/{device_id}/calibration` usata dall'app.

## Dove osservare i dati

- **Node-RED** (`http://localhost:1880`): nella sidebar Debug. I nodi
  `DEBUG 1`-`DEBUG 4` mostrano rispettivamente MQTT originale, JSON,
  postura normalizzata e device normalizzato. Sono disattivati inizialmente
  per evitare che ECG e stream veloci saturino l'editor; abilitarli uno alla
  volta dal pulsante del nodo.
- **FastAPI** (`http://localhost:8000/docs`):
  `/api/v1/posture/latest`, `/api/v1/device/latest` e `/health`.
- **Grafana** (`http://localhost:3000`): dashboard
  `SmartBack - Monitoraggio posturale`, aggiornata ogni secondo.
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

Il backend applica un filtro EMA al pitch e al roll (`POSTURE_EMA_ALPHA=0.5`)
e un'isteresi predefinita di 2 gradi. Per esempio, una deviazione entra nella
fascia moderata a 10 gradi ma ne esce soltanto quando rientra sotto 8 gradi.
Questo evita oscillazioni rapide degli alert vicino alle soglie.

Se dopo un primo campione non arrivano nuovi dati `ACC_GYRO` per
`DATA_STALE_SECONDS` (10 secondi per impostazione predefinita), il backend
pubblica `DATA_STREAM_STALE`. Alla ripresa pubblica `DATA_STREAM_RESTORED`.

La calibrazione imposta contemporaneamente il riferimento di pitch e roll:

```json
{
  "device_id": "tshirt002",
  "reference_pitch_deg": 76.4,
  "reference_roll_deg": 1.2
}
```

Il riferimento viene salvato in SQLite e ricaricato dopo i riavvii del
backend. La calibrazione definisce lo zero del paziente: le soglie non sono
angoli assoluti del sensore, ma deviazioni rispetto a questo riferimento.
Il pulsante e attivo soltanto mentre la maglia del paziente selezionato sta
trasmettendo dati recenti.

La convenzione esposta alle interfacce e:

- pitch positivo: inclinazione in avanti;
- pitch negativo: inclinazione all'indietro;
- pitch zero: posizione fissata durante la calibrazione.

Le soglie pitch usano i campi storici `moderate_deviation_deg` e
`marked_deviation_deg` per compatibilita con l'app. Le soglie roll sono
`moderate_roll_deg` e `marked_roll_deg`.

Gli alert transitano su `smartback/alerts/device` e
`smartback/alerts/posture`, vengono mostrati dal nodo
`DEBUG ALERT ATTIVI/RISOLTI` e salvati nella measurement InfluxDB `alerts`.

Node-RED confronta inoltre il numero progressivo `samplenum` dei pacchetti
`ACC_GYRO`. Un salto genera `ACC_SEQUENCE_GAP` già all'ingresso. Se il salto è
visibile anche nell'output Thonny, la perdita è avvenuta prima della
pubblicazione MQTT; se Thonny mostra sequenze complete ma Node-RED rileva un
salto, la perdita è nel tratto ESP32 -> broker.

Per tornare al simulatore, avviare esplicitamente il profilo:

```bash
docker compose --profile simulation up -d --build simulator
```

Il simulatore ufficiale non usa topic alternativi: emula direttamente l'ESP32
su `unisadiem/smartshirt/<device>/#` e attraversa lo stesso flusso Node-RED.
Configurazione, scenari e controlli sono descritti in
[`SMART_SHIRT_SIMULATOR.md`](SMART_SHIRT_SIMULATOR.md).

# Simulatore ufficiale della smart shirt

Il simulatore sostituisce temporaneamente il tratto **maglia BLE + ESP32** e
pubblica lo stesso contratto MQTT prodotto dai file MicroPython immutabili.
Tutto ciò che segue Mosquitto è condiviso con il dispositivo reale:

```text
Simulatore oppure ESP32
  -> unisadiem/smartshirt/<device>/#
  -> Node-RED
  -> smartback/normalized/*
  -> FastAPI -> InfluxDB -> Grafana
```

Non pubblica direttamente sui topic normalizzati. Questo permette di provare
anche filtri, diagnostica, perdita pacchetti e trasformazioni Node-RED.

## Avvio e arresto

Avviare lo stack e poi il solo profilo esplicito:

```bash
docker compose up -d --build
docker compose --profile simulation up -d --build simulator
```

Arrestarlo prima di collegare la maglia reale:

```bash
docker compose stop simulator
```

Il servizio usa `restart: "no"` e non riparte automaticamente. Per evitare di
mescolare dati sintetici e reali, simulatore ed ESP32 non devono essere attivi
contemporaneamente per lo stesso paziente.

Il simulatore riproduce il contratto osservabile **a valle del parser BLE**:
topic MQTT, JSON, tipi numerici, numero di campioni, sequenze e periodicita. Non
simula radio BLE, RSSI o discovery GATT, che restano responsabilita del firmware
immutabile e non sono visibili ai componenti server.

## Contratto emulato

Le maglie simulate vengono registrate dalla Home medica con un identificativo
distinto, per esempio `tshirt-sim-003`. FastAPI pubblica l'elenco tramite MQTT
retained e il simulatore attiva dinamicamente una sorgente indipendente per
ciascuna maglia registrata. I topic risultanti sono:

```text
unisadiem/smartshirt/tshirt-sim-003/ACC_GYRO
unisadiem/smartshirt/tshirt-sim-003/BATTERY_INFO
unisadiem/smartshirt/tshirt-sim-003/SYSTEM_INFO
```

`ACC_GYRO` contiene 16 campioni interi e viene prodotto ogni 0,64 secondi con
frequenza dichiarata di 25 Hz, coerentemente con il parser ESP32. Batteria e
stato di sistema hanno gli stessi nomi e tipi del relativo `to_json()`.

## Scenari

Configurare in `.env`:

```env
SIMULATION_SCENARIO=day-cycle
```

Scenari disponibili:

- `day-cycle`: neutro, avanti, neutro, indietro, neutro, destra, neutro,
  sinistra e deviazione marcata; ciclo deterministico;
- `neutral`: postura neutra continua, utile per calibrazione e stabilità;
- `manual`: angoli fissi definiti da `SIMULATOR_PITCH_DEG` e
  `SIMULATOR_ROLL_DEG` nell'ambiente del servizio.

Le principali opzioni sono riportate in `.env.example`. Il seed fisso rende le
prove ripetibili pur conservando un rumore realistico sui 16 campioni.

## Prove di perdita dati

Per saltare deterministicamente un pacchetto ogni 10 e verificare sia
`ACC_SEQUENCE_GAP` sia `DATA_LOSS` in Node-RED:

```env
SIMULATOR_DROP_EVERY_N_PACKETS=10
SIMULATOR_REPORT_DATALOSS_ON_DROP=true
```

Lasciare `SIMULATOR_DROP_EVERY_N_PACKETS=0` durante il normale monitoraggio.

## Verifica rapida

```bash
docker compose logs -f simulator
docker compose exec backend python tools/mqtt_probe.py
```

Nel probe devono comparire prima i topic `unisadiem/...`, poi
`smartback/shirt/raw/...` e infine `smartback/normalized/posture` o
`smartback/normalized/device`. Nella Home medica è sufficiente aggiungere una
maglia, assegnarla a un paziente e aprirne la scheda: la distinzione tecnica
fra hardware e simulatore non viene mostrata al medico. Il simulatore può
alimentare contemporaneamente le maglie fittizie, mentre `tshirt002` /
`Maglia 2` resta internamente riservata ai dati fisici reali.

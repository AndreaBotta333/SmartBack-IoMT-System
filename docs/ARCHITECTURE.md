# Architettura SmartBack

Il flusso di riferimento del progetto e:

```text
Smart shirt / ESP32 ─┐
                     ├─> Mosquitto ─> Node-RED ─> FastAPI ─> InfluxDB / SQLite
Simulatore Python ───┘                              │
                                                   ├─> WebSocket / REST -> app
                                                   └─> InfluxDB -> Grafana
```

## Responsabilita

1. **Generazione dati**: la smart shirt reale e il simulatore sono sorgenti
   alternative. Non devono essere attivi insieme con lo stesso paziente/device.
2. **Ingestion**: Mosquitto trasporta i messaggi MQTT. I topic raw sono
   imposti dall'ESP32 nel formato
   `unisadiem/smartshirt/<device>/<packet-type>`.
3. **Normalizzazione**: Node-RED valida e converte il formato specifico della
   sorgente nei topic stabili `smartback/normalized/posture` e
   `smartback/normalized/device`. Conserva tutti i pacchetti della maglia nella
   measurement InfluxDB `shirt_raw`.
4. **Logica e archiviazione**: FastAPI valida nuovamente il contratto, calcola
   orientamento/deviazione/alert, salva le serie elaborate in InfluxDB e usa
   SQLite per utenti, sessioni e associazioni medico-paziente.
5. **Utenti finali**: l'app usa REST e WebSocket; Grafana legge InfluxDB.

L'ESP32/gateway deve occuparsi di acquisizione e trasmissione. Le soglie e i
calcoli posturali restano nel backend, così possono cambiare senza riflash del
dispositivo.

## Organizzazione backend iniziale

```text
backend/
├── app/
│   ├── __init__.py
│   ├── config.py           # configurazione da environment
│   ├── device_contract.py  # schemi dei messaggi normalizzati
│   └── main.py             # lifecycle, API, auth e orchestrazione (da separare ancora)
└── tools/
    └── mqtt_probe.py       # osservazione del traffico per commissioning
```

La prossima separazione naturale, dopo aver osservato i pacchetti reali, e in
`auth.py`, `crud.py`, `database.py`, `influx_manager.py`, `mqtt_handler.py`,
`models.py` e `schemas.py`. Non viene anticipata completamente ora per evitare
di cristallizzare assunzioni sul protocollo della shirt prima del test reale.

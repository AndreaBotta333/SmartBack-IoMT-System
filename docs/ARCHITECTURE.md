# Architettura SmartBack

Il flusso di riferimento del progetto e:

```text
Smart shirt / ESP32 ─┐
                     ├─> Mosquitto ─> Node-RED ─> FastAPI ─> InfluxDB / SQLite
Simulatore Python ───┘                              │
                                                   ├─> WebSocket / REST -> app
                                                   └─> InfluxDB -> Grafana
                                                                        ↑
                                         login SmartBack (solo medico) -> gateway
```

## Responsabilita

1. **Generazione dati**: la smart shirt reale e il simulatore sono sorgenti
   alternative. Non devono essere attivi insieme con lo stesso paziente/device.
2. **Ingestion**: Mosquitto trasporta i messaggi MQTT. I topic raw sono
   imposti dall'ESP32 nel formato
   `unisadiem/smartshirt/<device>/<packet-type>`.
3. **Normalizzazione**: Node-RED valida e converte il formato specifico della
   sorgente nei topic stabili `smartback/normalized/posture` e
   `smartback/normalized/device`. Conserva nella measurement InfluxDB
   `shirt_raw` soltanto i pacchetti utili al monitoraggio attuale o previsto:
   accelerometro, batteria, perdita dati e stato del sistema.
4. **Logica e archiviazione**: FastAPI valida nuovamente il contratto, calcola
   orientamento/deviazione/alert, salva le serie elaborate in InfluxDB e usa
   SQLite per utenti, sessioni e associazioni medico-paziente.
5. **Utenti finali**: l'app usa REST e WebSocket. Grafana legge InfluxDB ed e
   raggiungibile attraverso un gateway che accetta soltanto sessioni SmartBack
   appartenenti a medici verificati.

## Storico persistente

InfluxDB conserva lo storico con retention infinita. Grafana lo legge per la
vista medica; paziente e medico nell'app passano invece dagli endpoint FastAPI,
che applicano identita e associazione medico-paziente. Il contratto condiviso,
gli intervalli e le risposte sono descritti in `docs/HISTORY_API.md`.

L'ESP32/gateway deve occuparsi di acquisizione e trasmissione. Le soglie e i
calcoli posturali restano nel backend, così possono cambiare senza riflash del
dispositivo.

I dati `ACC_GYRO` vengono mantenuti anche in previsione della futura
funzionalita di stima del tempo trascorso seduti. Con il solo orientamento del
torso la distinzione seduto/in piedi richiedera una fase di calibrazione e
validazione specifica.

## Organizzazione backend iniziale

```text
backend/
├── app/
│   ├── __init__.py
│   ├── config.py           # configurazione da environment
│   ├── database.py         # inizializzazione e migrazioni SQLite
│   ├── device_contract.py  # schemi dei messaggi normalizzati
│   ├── influx_manager.py   # persistenza e query delle serie temporali
│   ├── mqtt_handler.py     # ingestion, stato realtime, watchdog e alert
│   ├── posture_service.py  # calibrazione, smoothing e soglie pitch/roll
│   └── main.py             # API, autenticazione e lifecycle
└── tools/
    └── mqtt_probe.py       # osservazione del traffico per commissioning
```

`main.py` conserva gli endpoint e l'autenticazione per mantenere compatibilita
con l'app corrente. Calcolo posturale, MQTT, database e InfluxDB non dipendono
piu direttamente dagli endpoint FastAPI.

## Pitch e roll

La calibrazione registra un riferimento indipendente per pitch e roll. Il
motore calcola:

- `pitch_deviation_deg`;
- `roll_deviation_deg`;
- `dominant_axis`;
- stato separato `pitch_status` e `roll_status`.

Per compatibilita, `deviation_deg` resta disponibile e contiene la deviazione
con valore assoluto maggiore. Le soglie predefinite sono configurabili
separatamente:

```env
MODERATE_DEVIATION_DEG=10
MARKED_DEVIATION_DEG=20
MODERATE_ROLL_DEG=10
MARKED_ROLL_DEG=20
```

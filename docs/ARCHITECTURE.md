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
   Il simulatore emula il contratto MQTT dell'ESP32 e non bypassa Node-RED; e
   disponibile solo tramite il profilo Docker Compose `simulation`.
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
   SQLite per utenti, sessioni di autenticazione e monitoraggio notturno,
   associazioni medico-paziente, inventario delle magliette e storico delle
   loro assegnazioni.
5. **Utenti finali**: l'app usa REST e WebSocket. Grafana legge InfluxDB ed e
   raggiungibile attraverso un gateway che accetta soltanto sessioni SmartBack
   appartenenti a medici verificati.

La struttura dei due database, le relative responsabilità e il flusso di
registrazione dei medici sono descritti in `docs/DATABASES.md`.

## Storico persistente

InfluxDB conserva lo storico con retention infinita. Grafana lo legge per la
vista medica; paziente e medico nell'app passano invece dagli endpoint FastAPI,
che applicano identita e associazione medico-paziente. Il contratto condiviso,
gli intervalli e le risposte sono descritti in `docs/HISTORY_API.md`.

Gli alert restano disponibili dalla prima rilevazione, ma vengono mostrati
entro l'intervallo temporale selezionato e associati alla relativa sessione di
monitoraggio. La sessione inizia con il primo campione valido, oppure con la
ripresa successiva a un'interruzione dichiarata dal watchdog. Gli alert storici
privi di identificativo sono conservati come `Sessione precedente`.

## Monitoraggio notturno

Il paziente dall'app o il medico associato dalla dashboard possono attivare
esplicitamente la modalita notturna. Entrambi possono arrestarla, mentre il
medico puo inoltre consultarne sessioni e riepiloghi. SQLite
conserva identita, maglia usata, stato e riepilogo di ogni sessione. InfluxDB
ospitera la serie temporale delle posizioni `supino`, `prono`, `decubito
destro`, `decubito sinistro` e `sconosciuto`.

La sessione resta aperta durante brevi assenze di telemetria: una disconnessione
non deve essere interpretata come fine del sonno. Il contratto iniziale e gli
endpoint sono descritti in `docs/NIGHT_MONITORING.md`.

Grafana espone una dashboard medica notturna separata, filtrabile per paziente
e sessione. Legge la measurement InfluxDB `night_position`; l'attivazione della
modalita e condivisa tra app del paziente e controllo medico autenticato.

## Portale medico e assegnazione delle magliette

Dopo l'accesso il medico entra nella Home SmartBack. La Home interroga FastAPI
e mostra solo i pazienti presenti in `doctor_patients`, oltre all'inventario
`devices`. Ogni legame maglia-paziente produce una nuova riga in
`device_assignments`: quando la maglia viene liberata la riga riceve
`released_at`, senza essere cancellata.

Ogni maglia appartiene all'inventario di un solo medico tramite
`devices.owner_doctor_id`. `doctor_device_number` è un identificativo interno
progressivo, parte da `0` ed è indipendente per ciascun medico; non viene mai
inserito manualmente. Il `device_id` tecnico di una maglia reale (per esempio
`tshirt002`) viene acquisito automaticamente dalla telemetria MQTT: finché non
ha proprietario compare tra le maglie rilevate disponibili e il medico deve
confermarne esplicitamente l'acquisizione. Per le maglie di test, FastAPI genera
invece un codice tecnico univoco e configura il simulatore senza richiedere un
codice al medico. Le API della Home, di assegnazione, rilascio e rimozione
filtrano sempre per il proprietario.

Il medico può creare dalla Home un profilo clinico usando soltanto il codice
fiscale, anche se il paziente non ha ancora un account. Il profilo nasce con
`account_registered=0` e può ricevere immediatamente una maglia, sessioni e
telemetria. Quando il paziente si registra dall'app con lo stesso codice
fiscale, FastAPI completa quel medesimo record (`account_registered=1`) con
nome, cognome, email e credenziali: `id`, `patient_code`, assegnazioni e storico
non cambiano.

FastAPI pubblica le assegnazioni attive come configurazioni MQTT retained su
`smartback/config/device-assignments/<device_id>`. Node-RED usa questa mappa per
attribuire i pacchetti immutabili dell'ESP32 al paziente corretto prima della
normalizzazione. Una maglia esplicitamente liberata continua a conservare il
raw, ma non alimenta più il monitoraggio clinico del precedente paziente.

L'inventario distingue `source_type=physical` e `source_type=simulated`.
`tshirt002`, mostrata come `Maglia 2`, è la sorgente fisica reale disponibile.
Le sorgenti simulate registrate dalla Home vengono pubblicate anche su
`smartback/config/simulated-devices/<device_id>`; un solo processo simulatore
può quindi emulare più maglie fittizie mantenendo topic e sequenze separati.

Le rimozioni dal portale sono logiche. Rimuovere un paziente cancella soltanto
il collegamento `doctor_patients`; account e serie InfluxDB restano intatti.
Rimuovere una maglia valorizza `devices.archived_at` e chiude l'eventuale
assegnazione attiva. Le righe di `device_assignments` e tutta la telemetria
storica non vengono eliminate.

L'ESP32/gateway deve occuparsi di acquisizione e trasmissione. Le soglie e i
calcoli posturali restano nel backend, così possono cambiare senza riflash del
dispositivo.

I dati `ACC_GYRO` vengono mantenuti anche in previsione della futura
funzionalita di stima del tempo trascorso seduti. Con il solo orientamento del
torso la distinzione seduto/in piedi richiedera una fase di calibrazione e
validazione specifica.

## Organizzazione backend

```text
backend/
├── app/
│   ├── __init__.py
│   ├── config.py           # configurazione da environment
│   ├── main.py             # solo entrypoint ASGI
│   ├── bootstrap.py        # composition root e wiring dei controller
│   ├── composition.py      # costruzione di repository e servizi
│   ├── api/                # controller, dipendenze e configurazione FastAPI
│   ├── domain/             # postura e monitoraggio notturno puri
│   ├── schemas/            # contratti HTTP e messaggi Node-RED
│   ├── services/           # casi d'uso applicativi
│   ├── repositories/       # persistenza SQLite per dominio
│   ├── infrastructure/     # MQTT, InfluxDB, Expo, SQLite e lifecycle
│   └── presentation/       # pagine e asset del portale medico
└── tools/
    └── mqtt_probe.py       # osservazione del traffico per commissioning
```

La migrazione verso controller sottili, servizi applicativi e repository è
incrementale per mantenere compatibilità con app, Grafana e dati esistenti.
Struttura target e regole di dipendenza sono descritte in
`docs/BACKEND_ARCHITECTURE.md`.

## Pitch e roll

La calibrazione registra un riferimento indipendente per pitch e roll. Il
backend lo conserva in SQLite per dispositivo e paziente, così non viene perso
al riavvio. Il motore calcola:

- `pitch_deviation_deg`;
- `roll_deviation_deg`;
- `dominant_axis`;
- stato separato `pitch_status` e `roll_status`.

Il pitch usa la convenzione clinica avanti positivo e indietro negativo. Le
soglie sono applicate al valore assoluto della deviazione dalla calibrazione,
non all'angolo grezzo del sensore.

Per compatibilita, `deviation_deg` resta disponibile e contiene la deviazione
con valore assoluto maggiore. Le soglie predefinite sono configurabili
separatamente:

```env
MODERATE_DEVIATION_DEG=10
MARKED_DEVIATION_DEG=20
MODERATE_ROLL_DEG=10
MARKED_ROLL_DEG=20
```

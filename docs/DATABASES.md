# Database e persistenza

SmartBack usa due database applicativi distinti. I dati non vengono duplicati
automaticamente tra i due: ogni informazione viene salvata nell'archivio
coerente con la propria natura.

## Quadro generale

| Archivio | Tecnologia | Responsabilità |
|---|---|---|
| Database relazionale | SQLite | Identità, autenticazione, relazioni, configurazioni e sessioni |
| Database di serie temporali | InfluxDB 2.x | Telemetria, postura, posizioni notturne, stato della maglia e alert |

Grafana dispone anche di un archivio tecnico interno nel volume
`smartback-grafana-data`, usato esclusivamente dal prodotto Grafana per la
propria configurazione e il proprio stato. Non è un database del dominio
SmartBack. Analogamente, i bucket InfluxDB `_monitoring` e `_tasks` sono
archivi interni di InfluxDB e non contengono i dati clinici dell'applicazione.

## SQLite

Il database SQLite è configurato tramite `AUTH_DB_PATH` e, nel container
backend, si trova normalmente in `/app/data/smartback.db`. Il volume Docker
`smartback-backend-data` ne rende persistente il contenuto.

Lo schema viene inizializzato in
`backend/app/infrastructure/database.py` e comprende:

| Tabella | Contenuto |
|---|---|
| `users` | Account medici e pazienti, credenziali cifrate, ruolo e stato di registrazione |
| `sessions` | Token delle sessioni SmartBack |
| `push_tokens` | Token dei dispositivi mobili per le notifiche |
| `app_notifications` | Notifiche persistenti destinate agli utenti dell'app |
| `doctor_patients` | Associazioni tra medici e pazienti |
| `monitoring_configs` | Soglie e configurazione del monitoraggio posturale |
| `device_calibrations` | Riferimenti di calibrazione pitch e roll |
| `devices` | Inventario delle smart shirt |
| `device_assignments` | Storico delle assegnazioni maglia-paziente |
| `night_monitoring_sessions` | Stato e riepilogo delle sessioni notturne |

SQLite è la fonte autorevole per identità e autorizzazioni. Le password non
sono conservate in chiaro: il database contiene hash e salt.

## InfluxDB

InfluxDB usa normalmente:

- organizzazione `smartback`;
- bucket applicativo `posture`;
- volume Docker `smartback-influxdb-data`.

InfluxDB non espone tabelle SQL. I concetti principali sono:

- **bucket**: contenitore e politica di conservazione;
- **measurement**: categoria della serie, simile concettualmente a una tabella;
- **tag**: metadato indicizzato usato per i filtri, come `patient_id` e
  `device_id`;
- **field**: valore misurato, come pitch, roll o livello batteria;
- **point**: measurement, tag e field associati a un timestamp.

Il bucket `posture` contiene le seguenti measurement applicative:

| Measurement | Contenuto | Componente che scrive |
|---|---|---|
| `posture` | Pitch, roll, deviazioni, calibrazioni e durate | FastAPI |
| `night_position` | Posizione notturna classificata nel tempo | FastAPI |
| `night_session_state` | Stato temporale della sessione notturna | FastAPI |
| `shirt_raw` | Pacchetti utili ricevuti e normalizzati | Node-RED |
| `device_status` | Batteria e stato della maglia | Node-RED |
| `alerts` | Apertura e risoluzione degli alert | Node-RED |

Una measurement compare nell'Explorer di InfluxDB solo dopo la scrittura di
almeno un punto compatibile con l'intervallo temporale selezionato. L'elenco
delle measurement è inoltre scorrevole: una parte può trovarsi sotto l'area
visibile. Le tabelle SQLite non possono comparire nell'Explorer InfluxDB perché
appartengono a un database differente.

## Utilizzo da parte di app e Grafana

L'app mobile non possiede credenziali InfluxDB e non interroga direttamente il
bucket. Usa le API REST e i WebSocket FastAPI; il backend:

1. identifica l'utente tramite SQLite;
2. verifica ruolo e associazioni medico-paziente;
3. interroga InfluxDB quando servono telemetria e storico;
4. restituisce soltanto i dati autorizzati.

Il portale medico usa FastAPI e SQLite per accesso, elenco pazienti,
inventario, assegnazioni, calibrazioni e comandi. I pannelli Grafana possono
invece interrogare direttamente InfluxDB attraverso il datasource provisionato
dal progetto.

```text
App mobile ───────────────> FastAPI ──> SQLite
                                └─────> InfluxDB

Portale medico ───────────> FastAPI ──> SQLite
Pannelli temporali Grafana ───────────> InfluxDB
```

## Registrazione di un medico

La registrazione di un medico non legge e non scrive InfluxDB.

Il flusso attuale è:

1. `RegisterRequest` valida nome, cognome, email, password e ruolo;
2. il valore inserito come codice medico viene confrontato in memoria con
   `MEDICAL_REGISTRATION_CODE`, configurato tramite variabile d'ambiente;
3. `AuthService` consulta SQLite per verificare che l'email non sia già
   registrata;
4. la password viene trasformata in hash con un salt;
5. il nuovo account con ruolo `doctor` viene inserito in `users`;
6. dopo l'accesso, il token viene inserito in `sessions`.

Il codice medico attuale è quindi un **codice di registrazione SmartBack
condiviso**, non il numero personale del medico e non un dato salvato
nell'account. Non viene consultato un albo professionale o un database esterno:
il controllo dimostra soltanto che l'utente conosce il codice configurato per
il prototipo. Per una verifica professionale reale servirà integrare una fonte
autorevole o un processo amministrativo di approvazione.

| Operazione di registrazione | SQLite | InfluxDB |
|---|---:|---:|
| Verifica email già registrata | Sì | No |
| Confronto del codice di registrazione configurato | No, avviene in memoria | No |
| Salvataggio account e password cifrata | Sì | No |
| Creazione della sessione di accesso | Sì | No |
| Salvataggio di telemetria clinica | No | No |

InfluxDB verrà coinvolto solo quando arriveranno misurazioni o quando
un'interfaccia richiederà dati temporali già archiviati.

## Principio di separazione

La scelta dell'archivio dipende dal tipo di informazione:

- una modifica all'account, a una relazione o a una configurazione riguarda
  SQLite;
- una rilevazione associata a un istante riguarda InfluxDB;
- un caso d'uso può leggere entrambi, ma non deve replicare lo stesso record
  nei due database senza una precisa necessità applicativa.

# Riferimento sistematico del flow Node-RED

Questo documento descrive i **39 nodi** presenti nel file
`nodered/smartback/flows.json`. La numerazione segue l'ordine del file JSON e
serve come riferimento tecnico stabile: la posizione grafica dei nodi nel
canvas può invece cambiare.

## 1. Ruolo di Node-RED nell'architettura

Node-RED è il confine di ingestione tra le sorgenti MQTT e il resto di
SmartBack:

```text
ESP32 o simulatore
        |
        v
Mosquitto --> Node-RED --> topic MQTT normalizzati --> FastAPI
                  |
                  +--> InfluxDB
                  |
                  +--> alert tecnici e di qualità
```

Node-RED non calcola le inclinazioni cliniche e non applica la calibrazione
posturale. I suoi compiti sono:

1. mantenere le informazioni necessarie su assegnazioni e sorgenti simulate;
2. ricevere il protocollo della smart shirt senza modificarlo alla sorgente;
3. filtrare, arricchire e normalizzare i pacchetti;
4. inoltrare i contratti normalizzati al backend;
5. archiviare pacchetti raw, stato del dispositivo e alert;
6. trasformare gli errori tecnici del flow in alert osservabili.

## 2. Riepilogo dei nodi

| Categoria | Quantità |
|---|---:|
| Tab del flow | 1 |
| Nodi di configurazione | 2 |
| Commenti/separatori grafici | 4 |
| Ingressi MQTT | 4 |
| Uscite MQTT | 4 |
| Decodificatori JSON | 2 |
| Function | 7 |
| Scritture InfluxDB | 3 |
| Debug | 11 |
| Catch | 1 |
| **Totale** | **39** |

## 3. Configurazione generale

### Nodo 1 — `smartback-tab`

- **Tipo:** `tab`
- **Nome:** `SmartBack shirt ingestion`
- **Responsabilità:** contiene l'intero flow SmartBack.
- **Input/output:** nessuno; è il contenitore grafico e logico degli altri
  nodi.

### Nodo 2 — `cfg-smartback-mqtt`

- **Tipo:** configurazione `mqtt-broker`
- **Nome:** `SmartBack Mosquitto`
- **Connessione:** `mosquitto:1883`
- **Client ID:** `smartback-nodered`
- **Responsabilità:** fornisce una configurazione MQTT condivisa a tutti i
  nodi MQTT IN e MQTT OUT.
- **Comportamento operativo:**
  - pubblica `online` su `smartback/status/nodered` all'avvio;
  - pubblica `offline` alla chiusura regolare;
  - usa lo stesso messaggio `offline` come Last Will in caso di arresto
    inatteso;
  - mantiene la connessione con keep-alive di 60 secondi.

### Nodo 39 — `cfg-smartback-influxdb`

- **Tipo:** configurazione `influxdb`
- **Nome:** `SmartBack · InfluxDB 2`
- **Connessione:** `${INFLUXDB_URL}`, con fallback strutturale
  `http://influxdb:8086`
- **Versione:** InfluxDB 2.x
- **Responsabilità:** centralizza la connessione usata dai tre nodi di
  scrittura InfluxDB.
- **Credenziali:** il token non è scritto nel flow. Viene risolto dalla
  variabile d'ambiente `INFLUXDB_TOKEN` tramite `flows_cred.json`.

## 4. Sezione 1 — Configurazione dispositivi

Questa sezione aggiorna due mappe conservate nel contesto del flow:

- `deviceAssignments`: associa `device_id` a `patient_id`;
- `simulatedDevices`: indica quali device producono dati simulati.

Il contesto è in memoria: viene ricostruito dai messaggi retained MQTT dopo un
riavvio.

### Nodo 3 — `shirt-comment`

- **Tipo:** `comment`
- **Testo:** `1 · CONFIGURAZIONE DISPOSITIVI`
- **Responsabilità:** separatore puramente grafico.

### Nodo 4 — `mqtt-device-assignments`

- **Tipo:** `mqtt in`
- **Nome:** `MQTT IN · assegnazioni`
- **Topic sottoscritto:** `smartback/config/device-assignments/+`
- **Input:** configurazioni pubblicate dal backend per associare o liberare
  una maglia.
- **Output:** inoltra il messaggio al nodo 5.
- **Perché è un ingresso separato:** l'assegnazione non è telemetria e deve
  poter cambiare indipendentemente dai dati della maglia.

### Nodo 5 — `store-device-assignment`

- **Tipo:** `function`
- **Nome:** `Memorizza assegnazione`
- **Input atteso:** oggetto con almeno `device_id`, più `active` e
  `patient_id`.
- **Elaborazione:**
  1. scarta messaggi privi di `device_id`;
  2. legge `deviceAssignments` dal contesto del flow;
  3. salva il `patient_id` se l'associazione è attiva;
  4. salva `null` quando la maglia viene liberata;
  5. aggiorna lo stato visuale del nodo.
- **Output:** configurazione ricevuta, senza modificarne il significato, verso
  il nodo 6.
- **Effetto sul sistema:** i dati posturali e di batteria sono attribuiti al
  paziente corretto solo quando questa mappa contiene un'associazione valida.

### Nodo 6 — `debug-device-assignment`

- **Tipo:** `debug`
- **Nome:** `DEBUG · assegnazioni`
- **Stato predefinito:** attivo.
- **Mostra:** `msg.payload` dopo la memorizzazione.
- **Utilità:** permette di verificare immediatamente associazioni e
  disassociazioni.

### Nodo 7 — `mqtt-simulated-devices`

- **Tipo:** `mqtt in`
- **Nome:** `MQTT IN · sorgenti simulate`
- **Topic sottoscritto:** `smartback/config/simulated-devices/+`
- **Input:** attivazione o disattivazione tecnica di una sorgente simulata.
- **Output:** inoltra il messaggio al nodo 8.
- **Perché è separato:** la natura simulata della sorgente è un metadato
  tecnico e non deve comparire nell'interfaccia clinica.

### Nodo 8 — `store-simulated-device`

- **Tipo:** `function`
- **Nome:** `Memorizza sorgente`
- **Input atteso:** `device_id` e `active`.
- **Elaborazione:** aggiorna la mappa `simulatedDevices` nel contesto del flow.
- **Output:** nessuno.
- **Effetto sul sistema:** il nodo 12 imposta `quality` a `simulated` oppure
  `measured` senza cambiare il contratto dati esposto a medico e paziente.

## 5. Sezione 2 — Acquisizione e normalizzazione

È la pipeline principale:

```text
MQTT IN smart shirt
  -> Decodifica JSON
  -> Filtra dati utili
  -> Normalizza pacchetto
  -> MQTT normalizzato / InfluxDB / alert
```

### Nodo 38 — `ingestion-comment`

- **Tipo:** `comment`
- **Testo:** `2 · ACQUISIZIONE E NORMALIZZAZIONE`
- **Responsabilità:** separatore puramente grafico.

### Nodo 9 — `mqtt-shirt-all`

- **Tipo:** `mqtt in`
- **Nome:** `MQTT IN · smart shirt`
- **Topic sottoscritto:** `unisadiem/smartshirt/+/#`
- **Input:** tutti i pacchetti pubblicati dall'ESP32 e dai simulatori secondo
  il protocollo originale.
- **Uscite:**
  - nodo 10 per l'elaborazione;
  - nodo 19 per l'osservazione del messaggio MQTT completo.
- **Nota:** non richiede modifiche al codice presente sull'ESP32.

### Nodo 10 — `json-shirt`

- **Tipo:** `json`
- **Nome:** `Decodifica JSON`
- **Input:** payload MQTT testuale o binario contenente JSON.
- **Elaborazione:** converte `msg.payload` in un oggetto JavaScript.
- **Uscite:**
  - nodo 11 per il filtraggio;
  - nodo 20 per il debug del JSON decodificato.
- **Perché serve:** i Function successivi devono accedere a proprietà quali
  `samples`, `samplenum` e `state_of_charge`, non a una stringa JSON.

### Nodo 11 — `filter-monitor-shirt`

- **Tipo:** `function`
- **Nome:** `Filtra dati utili`
- **Tipi ammessi:** `ACC_GYRO`, `BATTERY_INFO`, `DATALOSS`, `SYSTEM_INFO`.
- **Elaborazione principale:**
  1. ricava `packetType` dal topic MQTT;
  2. scarta i pacchetti non utilizzati;
  3. conta per tipo i pacchetti ignorati;
  4. per `ACC_GYRO`, confronta `samplenum` con l'ultima sequenza ricevuta;
  5. se trova un salto, genera un alert `ACC_SEQUENCE_GAP`.
- **Output 1:** pacchetto valido verso il nodo 12.
- **Output 2:** eventuale alert sulla perdita di pacchetti verso il nodo 24.
- **Stato visuale:** mostra il tipo accettato oppure il totale dei pacchetti
  scartati.

### Nodo 12 — `adapt-shirt-packet`

- **Tipo:** `function`
- **Nome:** `Normalizza pacchetto`
- **Responsabilità:** è il punto centrale di adattamento tra il protocollo
  della maglia e i contratti interni SmartBack.
- **Validazioni iniziali:**
  - struttura corretta del topic;
  - payload presente e di tipo oggetto;
  - presenza del `device_id` nel topic.
- **Arricchimento comune:**
  - `device_id`;
  - `patient_id` ricavato dalle assegnazioni;
  - `packet_type`;
  - topic e timestamp sorgente;
  - timestamp di ricezione del gateway;
  - qualità `measured` o `simulated`.
- **Gestione `ACC_GYRO`:**
  1. opera soltanto se la maglia è assegnata;
  2. elimina i campioni privi di assi numerici `x`, `y`, `z`;
  3. calcola la media dei tre assi;
  4. normalizza il vettore rispetto alla sua magnitudine;
  5. produce `smartback/normalized/posture`.
- **Gestione `BATTERY_INFO`:**
  1. opera soltanto se la maglia è assegnata;
  2. limita la percentuale all'intervallo 0–100;
  3. produce `smartback/normalized/device`;
  4. genera alert per batteria bassa, critica o ripristinata quando cambia lo
     stato.
- **Gestione `DATALOSS`:** genera un alert `DATA_LOSS`.
- **Output 1:** pacchetto raw arricchito.
- **Output 2:** postura normalizzata.
- **Output 3:** stato normalizzato del dispositivo.
- **Output 4:** struttura `[fields, tags]` per InfluxDB.
- **Output 5:** eventuale alert dispositivo.
- **Scelta progettuale:** normalizza trasporto e formato, ma delega al backend
  calibrazione, smoothing, soglie, sessioni e logica clinica.

### Nodo 13 — `mqtt-shirt-raw`

- **Tipo:** `mqtt out`
- **Nome:** `MQTT OUT · raw interno`
- **Topic:** dinamico, impostato dal nodo 12 come
  `smartback/shirt/raw/{device_id}/{packet_type}`.
- **Responsabilità:** rende disponibile internamente il pacchetto originale
  arricchito con i metadati di ingestione.

### Nodo 14 — `mqtt-normalized-posture`

- **Tipo:** `mqtt out`
- **Nome:** `MQTT OUT · postura`
- **Topic dinamico:** `smartback/normalized/posture`.
- **Responsabilità:** consegna al backend i vettori posturali normalizzati.

### Nodo 15 — `mqtt-normalized-device`

- **Tipo:** `mqtt out`
- **Nome:** `MQTT OUT · dispositivo`
- **Topic dinamico:** `smartback/normalized/device`.
- **Responsabilità:** consegna al backend batteria e stato normalizzato della
  maglia.
- **Retain:** il messaggio di batteria è retained, così i nuovi consumer
  ricevono immediatamente l'ultimo stato noto.

### Nodo 16 — `influx-write-shirt-raw`

- **Tipo:** `influxdb out`
- **Nome:** `INFLUXDB · pacchetti raw`
- **Measurement:** `shirt_raw`
- **Precisione:** millisecondi.
- **Fields:** JSON completo del pacchetto e tempo di ricezione.
- **Tags:** `device_id`, `packet_type`.
- **Responsabilità:** conserva una traccia diagnostica dei pacchetti ricevuti.

### Nodo 31 — `prepare-device-influx`

- **Tipo:** `function`
- **Nome:** `Prepara stato dispositivo`
- **Input:** stato normalizzato prodotto dal nodo 12.
- **Validazioni:** richiede `device_id`, timestamp e percentuale di carica
  numerici.
- **Output:** payload InfluxDB `[fields, tags]`.
- **Fields:** `state_of_charge`, `charging`, `time`.
- **Tags:** `device_id`, `patient_id`.
- **Destinazioni:** nodi 32 e 33.

### Nodo 32 — `influx-write-device`

- **Tipo:** `influxdb out`
- **Nome:** `INFLUXDB · stato dispositivo`
- **Measurement:** `device_status`
- **Precisione:** millisecondi.
- **Responsabilità:** archivia lo storico di batteria e ricarica.

### Nodi di debug dell'acquisizione

| N. | ID | Nome | Stato iniziale | Contenuto |
|---:|---|---|---|---|
| 17 | `debug-shirt` | `DEBUG · raw arricchito` | disattivo | pacchetto raw dopo l'arricchimento |
| 18 | `debug-influx-error` | `DEBUG · scrittura raw` | disattivo | payload inviato alla scrittura raw |
| 19 | `debug-mqtt-input` | `DEBUG · MQTT ricevuto` | disattivo | intero messaggio MQTT in ingresso |
| 20 | `debug-json-parsed` | `DEBUG · JSON decodificato` | disattivo | payload convertito in oggetto |
| 21 | `debug-posture-normalized` | `DEBUG · postura` | disattivo | contratto di postura normalizzato |
| 22 | `debug-device-normalized` | `DEBUG · dispositivo` | disattivo | contratto di stato dispositivo |
| 33 | `debug-device-storage` | `DEBUG · scrittura stato` | disattivo | payload preparato per `device_status` |

Questi debug sono intenzionalmente disattivati per evitare un flusso continuo
e rumoroso nella sidebar. Possono essere attivati singolarmente durante la
diagnosi.

## 6. Sezione 3 — Alert e archiviazione

Questa sezione riceve sia alert prodotti dal backend sia alert tecnici
generati nel flow. Tutti attraversano lo stesso topic MQTT e la stessa
validazione prima dell'archiviazione.

### Nodo 23 — `alerts-comment`

- **Tipo:** `comment`
- **Testo:** `3 · ALERT E ARCHIVIAZIONE`
- **Responsabilità:** separatore puramente grafico.

### Nodo 24 — `mqtt-device-alert`

- **Tipo:** `mqtt out`
- **Nome:** `MQTT OUT · alert`
- **Topic dinamico:** normalmente `smartback/alerts/device`.
- **Input possibili:**
  - perdita di sequenza dal nodo 11;
  - batteria o data loss dal nodo 12;
  - errore operativo dal nodo 36.
- **Responsabilità:** pubblica sul bus MQTT gli alert generati internamente da
  Node-RED.

### Nodo 25 — `mqtt-alerts-in`

- **Tipo:** `mqtt in`
- **Nome:** `MQTT IN · alert`
- **Topic sottoscritto:** `smartback/alerts/+`.
- **Input:** tutti gli alert applicativi e tecnici.
- **Output:** nodo 26.
- **Perché non è un ciclo infinito:** il nodo 24 pubblica una volta l'alert; il
  nodo 25 lo riceve per validarlo e archiviarlo, senza ripubblicarlo.

### Nodo 26 — `json-alert`

- **Tipo:** `json`
- **Nome:** `Decodifica JSON`
- **Responsabilità:** converte il payload dell'alert in oggetto JavaScript.
- **Output:** nodo 27.

### Nodo 27 — `manage-alert`

- **Tipo:** `function`
- **Nome:** `Valida e prepara alert`
- **Validazioni minime:** richiede `device_id`, `code` e timestamp numerico.
- **Gestione sessione:**
  - usa `session_id` se presente;
  - conserva l'ultima sessione nota per device;
  - usa `legacy` solo per alert storici privi di sessione.
- **Output 1:** payload `[fields, tags]` verso InfluxDB e relativo debug.
- **Output 2:** alert arricchito con `session_id` e timestamp di ricezione,
  destinato al debug funzionale.
- **Fields InfluxDB:** `active`, `episode_started`, `message`, `time`.
- **Tags InfluxDB:** device, paziente, categoria, severità, codice e sessione.

### Nodo 28 — `influx-write-alert`

- **Tipo:** `influxdb out`
- **Nome:** `INFLUXDB · alert`
- **Measurement:** `alerts`
- **Precisione:** millisecondi.
- **Responsabilità:** rende persistenti gli alert per dashboard live e
  storici.

### Nodo 29 — `debug-alert`

- **Tipo:** `debug`
- **Nome:** `DEBUG · alert`
- **Stato predefinito:** attivo.
- **Mostra:** alert validato e arricchito.
- **Utilità:** osservazione immediata degli alert attivi e risolti.

### Nodo 30 — `debug-alert-storage`

- **Tipo:** `debug`
- **Nome:** `DEBUG · scrittura alert`
- **Stato predefinito:** disattivo.
- **Mostra:** struttura preparata per InfluxDB.

## 7. Sezione 4 — Gestione errori

Un **alert** descrive una condizione prevista dal dominio, ad esempio batteria
bassa o pacchetti mancanti. Un **errore di flow** è invece un malfunzionamento
tecnico inatteso di un nodo, ad esempio JSON non valido o eccezione in una
Function.

### Nodo 34 — `flow-errors-comment`

- **Tipo:** `comment`
- **Testo:** `4 · GESTIONE ERRORI`
- **Responsabilità:** separatore puramente grafico.

### Nodo 35 — `catch-flow-errors`

- **Tipo:** `catch`
- **Nome:** `Cattura errori flow`
- **Nodi sorvegliati:**
  - decodifica JSON della maglia;
  - filtro dei dati;
  - normalizzazione;
  - decodifica JSON degli alert;
  - validazione degli alert;
  - preparazione dello stato dispositivo.
- **Responsabilità:** intercetta le eccezioni tecniche emesse dai nodi
  sorvegliati, impedendo che restino visibili soltanto nei log.
- **Output:** nodo 36.

### Nodo 36 — `format-flow-error`

- **Tipo:** `function`
- **Nome:** `Crea alert operativo`
- **Elaborazione:**
  1. identifica il nodo che ha generato l'errore;
  2. recupera il messaggio tecnico;
  3. crea un alert `NODERED_FLOW_ERROR`;
  4. assegna categoria `ingestion` e severità `critical`.
- **Output 1:** alert verso il nodo 24 e quindi verso la normale pipeline
  MQTT di archiviazione.
- **Output 2:** copia leggibile verso il nodo 37.
- **Vantaggio:** gli errori operativi diventano persistenti e osservabili come
  il resto degli alert.

### Nodo 37 — `debug-flow-error`

- **Tipo:** `debug`
- **Nome:** `DEBUG · errori flow`
- **Stato predefinito:** attivo.
- **Mostra:** dettaglio dell'alert operativo derivato dall'errore.

## 8. Tracciamento completo per tipo di messaggio

### Pacchetto posturale

```text
9 -> 10 -> 11 -> 12
                  |-> 13 raw MQTT
                  |-> 14 postura normalizzata -> FastAPI
                  |-> 16 shirt_raw su InfluxDB
                  `-> debug opzionali
```

### Batteria

```text
9 -> 10 -> 11 -> 12
                  |-> 15 stato dispositivo -> FastAPI
                  |-> 31 -> 32 device_status su InfluxDB
                  `-> 24 eventuale alert batteria
```

### Alert

```text
backend oppure nodi 11/12/36
        -> MQTT smartback/alerts/+
        -> 25 -> 26 -> 27 -> 28 alerts su InfluxDB
                           `-> 29/30 debug
```

### Errore tecnico

```text
nodo sorvegliato -> 35 -> 36 -> 24 -> pipeline alert
                          `-> 37 debug
```

## 9. Regole di manutenzione

1. Non modificare i topic originali trasmessi dall'ESP32.
2. Aggiungere nuovi tipi di pacchetto prima al filtro del nodo 11 e poi alla
   normalizzazione del nodo 12.
3. Non inserire token o password direttamente in `flows.json`.
4. Usare i nodi `influxdb out` per le scritture, preparando nelle Function
   soltanto `[fields, tags]`.
5. Non spostare nel flow calibrazione, soglie o logica clinica: appartengono al
   backend.
6. Lasciare disattivi i debug ad alto volume quando non si sta diagnosticando
   il sistema.
7. Dopo modifiche manuali al canvas, non eseguire automaticamente
   `reorganize_flow.js`, perché ripristinerebbe il layout descritto nello
   script.
8. Dopo ogni modifica verificare almeno:
   - parsing valido di `flows.json`;
   - assenza di ID duplicati e collegamenti mancanti;
   - connessione MQTT;
   - scrittura delle tre measurement InfluxDB;
   - assenza di segreti nel repository.

# Architettura interna del backend

## Obiettivo

Il backend segue una separazione per responsabilità e dominio. Gli endpoint
HTTP devono tradurre richieste e risposte, non contenere query SQL, HTML,
algoritmi posturali o coordinamento MQTT.

```text
API / WebSocket / pagine Grafana
              |
              v
        servizi applicativi
              |
       +------+------+
       |             |
       v             v
   dominio       porte/repository
                     |
          +----------+----------+
          |          |          |
        SQLite    InfluxDB     MQTT
```

## Responsabilità

### `app/domain`

Regole pure del problema SmartBack:

- validazione del codice fiscale;
- classificazione posturale;
- soglie, isteresi e calibrazione;
- classificazione delle posizioni notturne.

Non dipende da FastAPI, SQLite, InfluxDB o MQTT.

### `app/schemas`

Contratti in ingresso e uscita:

- request e response delle API;
- messaggi normalizzati provenienti da Node-RED.

Gli schemi validano i dati, ma non eseguono operazioni applicative.

### `app/services`

Casi d’uso:

- autenticazione e sessioni;
- gestione pazienti del medico;
- inventario e assegnazione delle maglie;
- calibrazione;
- sessioni diurne e notturne;
- notifiche.

Ogni servizio coordina dominio e repository. Non genera HTML e non conosce i
dettagli del protocollo HTTP.

### `app/repositories`

Accesso ai dati:

- repository SQLite per identità, inventario e sessioni;
- repository InfluxDB per telemetria e storico.

Le query appartengono al repository del relativo dominio.

### `app/infrastructure`

Adattatori tecnici:

- client MQTT e gestione del ciclo di connessione;
- coordinamento della telemetria MQTT;
- InfluxDB;
- notifiche Expo;
- configurazione e lifecycle.

`infrastructure/telemetry.py` espone il coordinatore usato dal client MQTT.
Inventario rilevato, assegnazioni attive, simulatori e riepiloghi delle
sessioni notturne vengono letti e aggiornati tramite
`repositories/runtime_repository.py`; né `main.py` né il lifecycle contengono
più le relative query SQL.

### `app/api`

Controller FastAPI sottili, separati per consumatore e dominio:

- autenticazione e API dell’app;
- portale medico/Grafana;
- monitoraggio diurno;
- monitoraggio notturno;
- dispositivi;
- WebSocket;
- sistema.

Un controller valida la richiesta, invoca un servizio e traduce gli errori in
risposte HTTP.

La cartella è ulteriormente suddivisa in:

- `api/dependencies/`: autenticazione e altre dipendenze HTTP riutilizzabili;
- `api/endpoints/`: registrazione delle route dei singoli domini;
- `api/exception_handlers.py`: traduzione centralizzata degli errori
  applicativi;
- `api/routers.py`: composizione dei router e metadati OpenAPI.

Le API di autenticazione/account e delle notifiche sono state trasferite in
`api/endpoints`. I relativi controller non accedono direttamente a SQLite o al
client Expo, ma delegano rispettivamente ad `AuthService` e
`NotificationService`. La lettura dell'header Bearer e la validazione del
cookie Grafana sono isolate in `api/dependencies/auth.py`.

Anche le API dell'app dedicate ai pazienti del medico si trovano in
`api/endpoints/doctor_patients.py`. Elenco, associazione e configurazione delle
soglie delegano a `PatientService`; persistenza delle associazioni e delle
configurazioni appartiene a `PatientRepository`.

Le API di stato e inventario delle maglie sono registrate da
`api/endpoints/devices.py`. Acquisizione, creazione delle maglie di test,
assegnazione, rilascio e rimozione passano da `DeviceService` e
`DeviceRepository`; MQTT è usato dal servizio soltanto come adattatore per
pubblicare i cambiamenti di assegnazione. La calibrazione resta separata perché
appartiene al dominio posturale, non all'inventario.

Le operazioni di calibrazione sono esposte da
`api/endpoints/calibration.py`: calibrazione live, acquisizione immutabile del
campione al clic, conferma successiva e calibrazione manuale usano tutte
`CalibrationService`. Il controller traduce i conflitti conservando il
messaggio specifico prodotto dal caso d'uso, senza conoscere persistenza,
algoritmo posturale o protocollo MQTT.

Il monitoraggio notturno è esposto da
`api/endpoints/night_monitoring.py` per app e portale medico. Avvio, arresto,
stato, storico aggregato e dettaglio sessione delegano a
`NightMonitoringService`; tutte le query SQLite sono raccolte in
`NightSessionRepository`. Il formato pubblico delle sessioni è definito una
sola volta in `serializers/night_sessions.py`, mentre InfluxDB viene consultato
dal servizio soltanto per aggiungere le posizioni al dettaglio della sessione.

Il monitoraggio diurno è esposto da `api/endpoints/day_monitoring.py`.
Campione corrente, storico, disponibilità, sessioni e statistiche delegano a
`DayMonitoringService`, che coordina archivio temporale e profilo delle soglie.
La normalizzazione dell'intervallo richiesto resta nel livello API perché
traduce direttamente i parametri HTTP `minutes`, `start` ed `end`.

Gli endpoint informativi e diagnostici sono isolati in
`api/endpoints/system.py`. Il canale WebSocket è registrato da
`api/endpoints/realtime.py`, mentre la gestione delle connessioni e il routing
dei messaggi per paziente appartengono all'adattatore
`infrastructure/realtime.py`. In questo modo MQTT pubblica verso un'unica porta
di broadcasting senza conoscere FastAPI né la struttura delle connessioni.

Il portale medico è diviso per tipo di interfaccia:

- `api/endpoints/grafana_portal.py` espone autenticazione, sessione, Home,
  associazione dei pazienti e stato della modalità notte;
- `api/endpoints/grafana_pages.py` rende esclusivamente pagine e controlli HTML
  incorporati in Grafana.

Entrambi delegano autorizzazione e casi d'uso ai servizi applicativi. Le pagine
non eseguono query SQL: i selettori delle sessioni usano i servizi di
monitoraggio e i repository già definiti.

La composizione di repository e servizi è centralizzata in
`app/composition.py`: `ServiceContainer` risolve sempre gli adattatori runtime
correnti, evitando che i controller costruiscano direttamente le dipendenze.
Avvio e arresto di SQLite, InfluxDB, motori posturali e client MQTT sono invece
coordinati da `infrastructure/lifecycle.py`. Stato runtime, provider e
registrazione degli endpoint sono assemblati nel composition root
`bootstrap.py`; `main.py` espone soltanto l'oggetto ASGI.

La configurazione HTTP è raccolta in `api/application.py`: creazione di
FastAPI, middleware CORS, traduzione italiana degli errori di validazione,
statici, registrazione dei router e generazione OpenAPI. Il modulo
`bootstrap.py` fornisce lifespan, router già configurati e directory degli
asset.

La consegna delle notifiche è responsabilità di `NotificationService`, che
coordina destinatari, persistenza, deduplicazione temporale e invio Expo.
Il lifecycle riceve questo caso d'uso come callback e non conosce né token push
né dettagli del provider.

### `app/presentation`

HTML, CSS e JavaScript del portale medico. La presentazione non deve vivere nei
controller e non deve accedere direttamente al database.

## Regole di dipendenza

1. Il dominio non importa mai API o infrastruttura.
2. Gli schemi non interrogano database e broker.
3. I controller non contengono SQL.
4. I repository non generano risposte HTTP.
5. MQTT non decide autorizzazioni medico-paziente: riceve la configurazione dai
   servizi applicativi.
6. Le pagine Grafana consumano le stesse API del portale e non duplicano regole
   applicative.

## Migrazione incrementale

1. Estrarre schemi e regole pure.
2. Estrarre HTML, CSS e JavaScript da `main.py`.
3. Introdurre repository SQLite per autenticazione, pazienti e dispositivi.
4. Introdurre servizi applicativi per autenticazione e inventario.
5. Estrarre sessioni e monitoraggio notturno.
6. Separare i router in moduli mantenendo invariati URL e payload.
7. Ridurre `main.py` al solo entrypoint ASGI e trasferire la composizione in
   `bootstrap.py`.

Ogni passaggio deve mantenere verde la suite di test e non deve richiedere
migrazioni distruttive dei dati.
## Presentazione del portale medico

Le route HTTP non contengono più direttamente lo stile della pagina di accesso
e della Home medica. La presentazione è suddivisa in:

- `backend/app/presentation/templates/`: struttura HTML;
- `backend/app/presentation/static/`: CSS e comportamento JavaScript;
- `backend/app/presentation/templates.py`: caricamento e rendering dei template.

`api/endpoints/grafana_pages.py` autentica l'utente, prepara esclusivamente i
dati dinamici necessari e delega il rendering. `bootstrap.py` registra il
modulo fornendogli le dipendenze runtime. Gli endpoint e i contratti API
restano indipendenti dalla presentazione.

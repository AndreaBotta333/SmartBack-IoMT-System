# Monitoraggio notturno

## Confine della prima fondazione tecnica

La modalita notturna viene attivata e arrestata esclusivamente dal paziente.
Il backend collega ogni sessione alla maglia assegnata in quel momento e ne
conserva il ciclo di vita in SQLite. Il medico associato puo consultare lo
storico, ma non puo avviare o fermare la rilevazione al posto del paziente.

Nell'app il paziente usa il pulsante `MODALITÀ NOTTE`. L'attivazione abilita
automaticamente il tema scuro e sostituisce temporaneamente la vista posturale
diurna con la posizione notturna in tempo reale e le durate cumulate per
posizione. Il tema non puo essere
disattivato dalle Impostazioni finche la sessione notturna resta attiva.

Il backend classifica `supino`, `prono`, `decubito destro`, `decubito sinistro`
e `sconosciuto` direttamente dal vettore di gravita. Smoothing, isteresi e un
tempo minimo di stabilizzazione evitano cambi prodotti dal rumore o da una
transizione momentanea. La serie viene salvata nella measurement InfluxDB
`night_position` solo quando esiste una sessione notturna attiva.

La convenzione iniziale coincide con il simulatore: `-Z=prono`, `+Z=supino`,
`+X=decubito destro`, `-X=decubito sinistro`. Prima di un uso clinico i versi
devono essere confermati con la maglia fisica; non serve modificare l'ESP32.

## Ciclo di vita

Una sessione puo essere:

- `active`: monitoraggio notturno in corso;
- `completed`: arresto richiesto dal paziente;
- `interrupted`: chiusura tecnica esplicita, predisposta per watchdog o
  manutenzione futura.

Esiste al massimo una sessione attiva per paziente e per maglia. Una sessione
puo iniziare solo se il paziente ha una maglia assegnata, non liberata e non
archiviata. La disconnessione temporanea della maglia non chiude
automaticamente la sessione: i periodi senza telemetria verranno contabilizzati
come `data_gap_seconds` dalla pipeline di classificazione.

## API

Tutti gli endpoint richiedono una sessione SmartBack tramite Bearer token.

```text
POST /api/v1/night-monitoring/start
POST /api/v1/night-monitoring/stop
GET  /api/v1/night-monitoring/status?patient_id=<id>
GET  /api/v1/night-monitoring/history?patient_id=<id>&limit=50
GET  /api/v1/night-monitoring/sessions/<session_id>
```

`start` e `stop` sono riservati al paziente. `status`, `history` e il dettaglio
sono consultabili dal paziente oppure da un medico associato; per il medico il
parametro `patient_id` e obbligatorio dove previsto.

La risposta include durata, versione del classificatore e un riepilogo con i
secondi trascorsi in ciascuna posizione, cambi di posizione e assenza dati. Il
dettaglio include anche `positions`, cioe la sequenza persistita in InfluxDB.

## Simulazione

Per produrre ciclicamente tutte le posizioni senza la maglia reale impostare:

```env
SIMULATION_SCENARIO=night-cycle
```

Quando il paziente usa una maglia registrata come `simulated`, il backend
commuta automaticamente quel solo simulatore su `night-cycle` all'avvio della
sessione e lo riporta a `day-cycle` alla chiusura. La variabile d'ambiente resta
il valore iniziale e il fallback per i test manuali.

Il simulatore continua a passare da Mosquitto e Node-RED: il percorso osservato
dal classificatore e lo stesso della maglia reale.

## Vista medica Grafana

Le dashboard notturne sono raggiungibili dalla scheda del paziente nella Home
medica e dai collegamenti presenti in tutte le altre dashboard. Mantengono
separati monitoraggio diurno e notturno.

La vista live mostra:

- ultima posizione rilevata;
- timeline delle posizioni;
- distribuzione indicativa del tempo;

Lo storico notturno permette di selezionare intervallo e sessione, oppure tutte
le sessioni, e mostra una timeline unica. Supino, prono e i due decubiti sono
stati mutuamente esclusivi, quindi un solo grafico rende i passaggi piu chiari
di due grafici separati. Quattro contatori e una distribuzione riepilogano le
durate senza spezzare la sequenza temporale.

Le dashboard leggono esclusivamente `night_position`. Prima della prima sessione
notturna e quindi corretto che mostri `Nessun dato`.

Durante una sessione notturna FastAPI non alimenta la measurement posturale
diurna: la dashboard live diurna si svuota entro la propria finestra realtime e
non archivia la notte come postura diurna.

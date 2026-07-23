# Node-RED SmartBack

Docker utilizza esclusivamente `nodered/smartback` come directory `/data`.
La cartella `nodered/data` è materiale locale storico e non viene caricata
dallo stack.

La descrizione nodo per nodo dell'intero flow è disponibile in
[`docs/NODERED_FLOW_REFERENCE.md`](../docs/NODERED_FLOW_REFERENCE.md).

## Organizzazione del flow

Il tab `SmartBack shirt ingestion` è suddiviso in quattro corsie:

1. **Configurazione dispositivi**: mantiene in memoria assegnazioni
   maglia-paziente e l'elenco delle sorgenti simulate.
2. **Acquisizione e normalizzazione**: riceve il protocollo MQTT invariato
   dell'ESP32/simulatore, decodifica, filtra e produce i contratti normalizzati.
3. **Alert e archiviazione**: valida gli alert e salva le serie temporali.
4. **Gestione errori**: converte gli errori dei nodi in alert operativi.

I nodi `DEBUG` sono affiancati ai punti osservabili del percorso. Quelli più
verbosi sono disattivati di default e si possono abilitare dalla sidebar senza
modificare la pipeline.

## Scritture InfluxDB

Le tre measurement scritte direttamente da Node-RED sono:

- `shirt_raw`;
- `device_status`;
- `alerts`.

Le scritture usano `node-red-contrib-influxdb` in modalità InfluxDB 2.x.
Le Function preparano soltanto `msg.payload` nel formato `[fields, tags]`;
connessione, token, organizzazione e bucket appartengono al nodo di
configurazione `SmartBack · InfluxDB 2`.

Le credenziali non sono inserite nel flow. `flows_cred.json` contiene soltanto
il riferimento `${INFLUXDB_TOKEN}` e Node-RED risolve il valore dall'ambiente
Docker.

## Avvio

Il modulo aggiuntivo è installato nell'immagine dedicata:

```bash
docker compose up -d --build nodered
```

L'editor è disponibile su `http://localhost:1880`.

## Manutenzione del layout

`nodered/smartback/reorganize_flow.js` descrive in modo ripetibile posizione,
nomi e configurazione dei nodi introdotti durante la riorganizzazione. Dopo
eventuali modifiche manuali al canvas non va eseguito automaticamente, perché
riapplicherebbe il layout documentato nello script.

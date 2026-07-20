# SmartBack IoMT System

SmartBack è un prototipo IoMT per il monitoraggio posturale tramite smart t-shirt HOWDY Senior. Il sistema acquisisce e trasmette le misurazioni, le elabora nel backend e le rende disponibili attraverso dashboard e applicazione mobile.

La smart t-shirt e il simulatore sono sorgenti alternative. Il simulatore e ora
un profilo esplicito, cosi non puo contaminare per errore una sessione con il
dispositivo reale.

## Componenti principali

- **Mosquitto**: broker MQTT;
- **Node-RED**: gestione e normalizzazione del flusso IoT;
- **FastAPI**: backend, autenticazione e logica applicativa;
- **InfluxDB**: serie temporali posturali e dati del dispositivo;
- **SQLite**: utenti, sessioni, inventario magliette e storico delle assegnazioni;
- **Grafana**: dashboard di monitoraggio;
- **Expo / React Native**: applicazione mobile;
- **simulatore Python**: sorgente dati usata durante lo sviluppo senza t-shirt.

L'ESP32 è previsto esclusivamente per la trasmissione: i calcoli vengono eseguiti nel backend.

## Requisiti

- Docker Desktop;
- Visual Studio Code con estensione Dev Containers;
- Expo Go sul telefono;
- Mac e telefono collegati alla stessa rete locale per l'uso in modalità LAN.

## Prima configurazione

Creare il file locale `.env` partendo dal modello:

```bash
cp .env.example .env
```

Impostare in `.env` l'indirizzo IP corrente del computer:

```env
HOST_IP=192.168.1.100
```

Il file `.env` è escluso da Git e non deve essere pubblicato.

## Avvio dei servizi

Dalla cartella principale del progetto:

```bash
docker compose up -d --build
docker compose --profile mobile up -d --build mobile
```

Per una sessione senza smart shirt, avviare anche il simulatore:

```bash
docker compose --profile simulation up -d --build simulator
```

Servizi locali principali:

- API FastAPI: `http://localhost:8000/docs
- Node-RED: `http://localhost:1880`
- Portale medico e Grafana: `http://localhost:3000` (credenziali SmartBack con ruolo medico)
- InfluxDB: `http://localhost:8086`

## Avvio manuale dell'app mobile

1. Collegarsi con VS Code al container `smartback-mobile`.
2. Aprire il terminale del container.
3. Eseguire:

```bash
cd /workspace/app
npx expo start --lan --clear
```

4. Scansionare il QR con Expo Go.

Quando cambia la rete Wi-Fi, aggiornare `HOST_IP` in `.env`, ricreare il container mobile e generare un nuovo QR.

## Note di sviluppo

- Le notifiche push sono temporaneamente accantonate.
- Le soglie posturali attuali sono dimostrative e dovranno essere consolidate nella documentazione tecnica e tramite fonti mediche.
- L'architettura completa e descritta in `docs/ARCHITECTURE.md`.
- La procedura per il primo collegamento fisico e in `docs/SMART_SHIRT_COMMISSIONING.md`.
- Il backend applica soglie indipendenti per inclinazione pitch e roll.
- Grafana separa angoli, deviazioni, batteria, qualità del flusso e alert.
- Grafana e una vista medica in sola lettura, accessibile soltanto a utenti
  SmartBack verificati con ruolo `doctor`.
- La configurazione dell'accesso medico e descritta in
  `docs/GRAFANA_MEDICAL_ACCESS.md`.
- Il contratto dello storico persistente condiviso dalle interfacce e descritto
  in `docs/HISTORY_API.md`.
- Il simulatore fedele dell'ESP32, i suoi scenari e i controlli MQTT sono
  descritti in `docs/SMART_SHIRT_SIMULATOR.md`.
- La cartella `REPORT_TEMPORANEI` contiene il registro di sviluppo e dovrà essere eliminata dopo la preparazione della documentazione finale.

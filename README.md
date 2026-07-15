# SmartBack IoMT System

SmartBack è un prototipo IoMT per il monitoraggio posturale tramite smart t-shirt HOWDY Senior. Il sistema acquisisce e trasmette le misurazioni, le elabora nel backend e le rende disponibili attraverso dashboard e applicazione mobile.

> Al momento la smart t-shirt non è disponibile: il flusso dati viene riprodotto tramite un simulatore.

## Componenti principali

- **Mosquitto**: broker MQTT;
- **Node-RED**: gestione e normalizzazione del flusso IoT;
- **FastAPI**: backend, autenticazione e logica applicativa;
- **InfluxDB**: serie temporali posturali e dati del dispositivo;
- **SQLite**: utenti, sessioni e associazioni medico-paziente;
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

Servizi locali principali:

- API FastAPI: `http://localhost:8000`
- Node-RED: `http://localhost:1880`
- Grafana: `http://localhost:3000`
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
- La cartella `REPORT_TEMPORANEI` contiene il registro di sviluppo e dovrà essere eliminata dopo la preparazione della documentazione finale.


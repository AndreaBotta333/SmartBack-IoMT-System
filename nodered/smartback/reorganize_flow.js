const fs = require("fs");
const path = require("path");

const flowPath = path.join(__dirname, "flows.json");
const flow = JSON.parse(fs.readFileSync(flowPath, "utf8"));
const byId = new Map(flow.map((node) => [node.id, node]));

function update(id, values) {
  const node = byId.get(id);
  if (!node) throw new Error(`Nodo Node-RED non trovato: ${id}`);
  Object.assign(node, values);
  return node;
}

function place(id, x, y, name) {
  const values = { x, y };
  if (name) values.name = name;
  return update(id, values);
}

// Intestazioni: corsie separate, senza riquadri che appesantiscono il canvas.
place("shirt-comment", 250, 40, "1 · CONFIGURAZIONE DISPOSITIVI");
place("alerts-comment", 230, 620, "3 · ALERT E ARCHIVIAZIONE");
place("flow-errors-comment", 220, 820, "4 · GESTIONE ERRORI");

let ingestionComment = byId.get("ingestion-comment");
if (!ingestionComment) {
  ingestionComment = {
    id: "ingestion-comment",
    type: "comment",
    z: "smartback-tab",
    name: "2 · ACQUISIZIONE E NORMALIZZAZIONE",
    info: "Riceve il protocollo invariato di ESP32 e simulatori, conserva solo i dati utili e pubblica il contratto normalizzato.",
    x: 270,
    y: 200,
    wires: [],
  };
  flow.push(ingestionComment);
  byId.set(ingestionComment.id, ingestionComment);
}

// Configurazione dinamica dispositivo/paziente e sorgenti simulate.
place("mqtt-device-assignments", 180, 90, "MQTT IN · assegnazioni");
place("store-device-assignment", 470, 90, "Memorizza assegnazione");
place("debug-device-assignment", 730, 90, "DEBUG · assegnazioni");
place("mqtt-simulated-devices", 180, 140, "MQTT IN · sorgenti simulate");
place("store-simulated-device", 470, 140, "Memorizza sorgente");

// Pipeline principale, disposta da sinistra a destra.
place("mqtt-shirt-all", 170, 250, "MQTT IN · smart shirt");
place("json-shirt", 410, 250, "Decodifica JSON");
place("filter-monitor-shirt", 640, 250, "Filtra dati utili");
place("adapt-shirt-packet", 900, 250, "Normalizza pacchetto");

place("mqtt-shirt-raw", 1220, 210, "MQTT OUT · raw interno");
place("mqtt-normalized-posture", 1230, 260, "MQTT OUT · postura");
place("mqtt-normalized-device", 1230, 310, "MQTT OUT · dispositivo");
place("mqtt-device-alert", 1230, 680, "MQTT OUT · alert");

place("prepare-device-influx", 1210, 360, "Prepara stato dispositivo");
place("influx-write-device", 1490, 360, "INFLUXDB · stato dispositivo");
place("influx-write-shirt-raw", 1230, 410, "INFLUXDB · pacchetti raw");

place("debug-mqtt-input", 170, 490, "DEBUG · MQTT ricevuto");
place("debug-json-parsed", 430, 490, "DEBUG · JSON decodificato");
place("debug-shirt", 700, 490, "DEBUG · raw arricchito");
place("debug-posture-normalized", 980, 490, "DEBUG · postura");
place("debug-device-normalized", 1230, 490, "DEBUG · dispositivo");
place("debug-influx-error", 1490, 410, "DEBUG · scrittura raw");
place("debug-device-storage", 1490, 490, "DEBUG · scrittura stato");

// Alert.
place("mqtt-alerts-in", 160, 670, "MQTT IN · alert");
place("json-alert", 390, 670, "Decodifica JSON");
place("manage-alert", 630, 670, "Valida e prepara alert");
place("influx-write-alert", 910, 650, "INFLUXDB · alert");
place("debug-alert", 920, 710, "DEBUG · alert");
place("debug-alert-storage", 1160, 650, "DEBUG · scrittura alert");

// Errori operativi.
place("catch-flow-errors", 170, 870, "Cattura errori flow");
place("format-flow-error", 440, 870, "Crea alert operativo");
place("debug-flow-error", 720, 900, "DEBUG · errori flow");

// Il nodo contrib InfluxDB usa payload [fields, tags] e una configurazione 2.x.
const influxShape = (measurement) => ({
  type: "influxdb out",
  influxdb: "cfg-smartback-influxdb",
  measurement,
  precision: "ms",
  retentionPolicy: "",
  // Campo legacy non usato in modalità 2.0, ma richiesto dal validatore UI
  // del plugin durante il primo caricamento del canvas.
  database: "smartback",
  precisionV18FluxV20: "ms",
  retentionPolicyV18Flux: "",
  org: "${INFLUXDB_ORG}",
  bucket: "${INFLUXDB_BUCKET}",
});

for (const [id, measurement] of [
  ["influx-write-shirt-raw", "shirt_raw"],
  ["influx-write-alert", "alerts"],
  ["influx-write-device", "device_status"],
]) {
  const node = update(id, influxShape(measurement));
  for (const obsolete of [
    "method", "ret", "paytoqs", "url", "tls", "persist", "proxy",
    "insecureHTTPParser", "authType", "senderr", "headers",
  ]) delete node[obsolete];
  node.wires = [];
}

// La configurazione è unica e usa esclusivamente variabili d'ambiente.
let influxConfig = byId.get("cfg-smartback-influxdb");
const influxConfigValues = {
  id: "cfg-smartback-influxdb",
  type: "influxdb",
  hostname: "influxdb",
  port: "8086",
  protocol: "http",
  database: "smartback",
  name: "SmartBack · InfluxDB 2",
  usetls: false,
  tls: "",
  influxdbVersion: "2.0",
  url: "${INFLUXDB_URL}",
  rejectUnauthorized: true,
  timeout: "10",
};
if (influxConfig) Object.assign(influxConfig, influxConfigValues);
else flow.push(influxConfigValues);

// Prepara i tre payload in formato nativo del nodo InfluxDB.
const normalizer = update("adapt-shirt-packet", {});
normalizer.func = normalizer.func
  .replace(
    /const escapedJson = JSON\.stringify\(envelope\)[\s\S]*?const influxMsg = \{[\s\S]*?\n\};\n\nlet postureMsg/,
    `const influxMsg = {\n    payload: [\n        {payload_json: JSON.stringify(envelope), time: receivedAt},\n        {device_id: deviceId, packet_type: packetType}\n    ]\n};\n\nlet postureMsg`
  );
normalizer.wires[3] = ["influx-write-shirt-raw", "debug-influx-error"];

const alert = update("manage-alert", {});
alert.func = `const a = msg.payload;
if (!a || !a.device_id || !a.code || !Number.isFinite(Number(a.timestamp))) {
    node.warn(\`Alert non valido da \${msg.topic}\`);
    return [null, null];
}
const sessions = context.get('monitoringSessions') || {};
if (a.session_id) sessions[a.device_id] = a.session_id;
const sessionId = a.session_id || sessions[a.device_id] || 'legacy';
sessions[a.device_id] = sessionId;
context.set('monitoringSessions', sessions);
const influxMsg = {
    payload: [
        {
            active: Boolean(a.active),
            episode_started: Boolean(a.episode_started),
            message: String(a.message || a.code),
            time: Number(a.timestamp)
        },
        {
            device_id: String(a.device_id),
            patient_id: String(a.patient_id || 'unknown'),
            category: String(a.category || 'unknown'),
            severity: String(a.severity || 'unknown'),
            code: String(a.code),
            session_id: String(sessionId)
        }
    ]
};
const debugMsg = {...msg, payload: {...a, session_id: sessionId, received_by_nodered_at: Date.now()}};
return [influxMsg, debugMsg];`;
alert.wires[0] = ["influx-write-alert", "debug-alert-storage"];

const device = update("prepare-device-influx", {});
device.func = `const p = msg.payload;
if (!p || !p.device_id || !Number.isFinite(Number(p.timestamp)) || !Number.isFinite(Number(p.state_of_charge))) {
    return null;
}
msg.payload = [
    {
        state_of_charge: Number(p.state_of_charge),
        charging: Boolean(p.charging),
        time: Number(p.timestamp)
    },
    {
        device_id: String(p.device_id),
        patient_id: String(p.patient_id || 'unknown')
    }
];
return msg;`;
device.wires = [["influx-write-device", "debug-device-storage"]];

// I debug delle scritture mostrano il payload pronto, non uno status HTTP.
for (const id of ["debug-influx-error", "debug-alert-storage", "debug-device-storage"]) {
  update(id, { complete: "payload", active: false });
}

fs.writeFileSync(flowPath, `${JSON.stringify(flow, null, 2)}\n`);

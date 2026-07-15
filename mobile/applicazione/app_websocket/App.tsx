// Importiamo React e alcuni strumenti fondamentali.
// useEffect serve per eseguire codice quando il componente parte.
// useMemo serve per calcolare dati derivati in modo efficiente.
// useState serve per creare variabili che, quando cambiano,
// aggiornano automaticamente la schermata.
import React, { useEffect, useMemo, useState } from "react";
import {
  SafeAreaView,
  Text,
  View,
  Dimensions,
  StyleSheet,
} from "react-native";
import { LineChart } from "react-native-chart-kit";

// Questo è un "tipo" TypeScript.
// Serve a descrivere com'è fatto un dato ricevuto dal backend.
type SensorSample = {
  timestamp: number;
  heartRate: number; // battiti cardiaci
  spo2: number; // ossigenazione sangue
  stepsPerMin: number; // passi al minuto
};

const BACKEND_HOST = "172.19.55.92"; // <-- cambia con IP del tuo PC
const HTTP_URL = `http://${BACKEND_HOST}:8000/health`;
const WS_URL = `ws://${BACKEND_HOST}:8000/ws/wearable`;

// Questo è il componente principale dell'app.
// In React, un componente è una funzione che restituisce interfaccia grafica.
export default function App() {
  // samples è la lista dei dati ricevuti dal sensore.
  // setSamples è la funzione per modificarla.
  // All'inizio è una lista vuota [].
  const [samples, setSamples] = useState<SensorSample[]>([]);
  const [connected, setConnected] = useState(false);

  const [healthStatus, setHealthStatus] = useState("non verificato");
  const [errorMessage, setErrorMessage] = useState("");

  // useEffect viene eseguito quando il componente viene caricato.
  // Qui apriamo la connessione WebSocket verso FastAPI.
  useEffect(() => {
    async function checkHealth() {
      try {
        setHealthStatus("controllo in corso...");

        const response = await fetch(HTTP_URL);

        if (!response.ok) {
          setHealthStatus(`errore HTTP ${response.status}`);
          return;
        }

        const data = await response.json();
        setHealthStatus(`backend ok: ${data.status}`);
      } catch (error) {
        setHealthStatus("backend non raggiungibile");
        setErrorMessage(String(error));
      }
    }

    checkHealth();
  }, []);

  useEffect(() => {
    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      setConnected(true);
      setErrorMessage("");
    };

    ws.onclose = (event) => {
      setConnected(false);
      setErrorMessage(
        `WebSocket chiuso. Code: ${event.code}, reason: ${event.reason || "nessuna"}`
      );
    };

    ws.onerror = (event) => {
      setConnected(false);
      setErrorMessage(`Errore WebSocket: ${JSON.stringify(event)}`);
    };

    ws.onmessage = (event) => {
      const sample: SensorSample = JSON.parse(event.data);
      setSamples((prev) => [...prev.slice(-19), sample]);
    };

    return () => {
      ws.close();
    };
  }, []);

  const chartData = useMemo(() => {
    const values = samples.map((s) => s.heartRate);

    return {
      labels: samples.map((_, i) => (i % 5 === 0 ? `${i}` : "")),
      datasets: [{ data: values.length ? values : [0] }],
    };
  }, [samples]);

  const latest = samples[samples.length - 1];

  return (
    <SafeAreaView style={styles.container}>
      <Text style={styles.title}>Wearable realtime dashboard</Text>

      <View style={styles.debugBox}>
        <Text>Health API: {healthStatus}</Text>
        <Text>WebSocket: {connected ? "connesso" : "disconnesso"}</Text>
        <Text>HTTP URL: {HTTP_URL}</Text>
        <Text>WS URL: {WS_URL}</Text>

        {errorMessage !== "" && (
          <Text style={styles.error}>Errore: {errorMessage}</Text>
        )}
      </View>

      {latest && (
        <View style={styles.cards}>
          <Text style={styles.card}>❤️ BPM: {latest.heartRate}</Text>
          <Text style={styles.card}>🫁 SpO₂: {latest.spo2}%</Text>
          <Text style={styles.card}>👟 Steps/min: {latest.stepsPerMin}</Text>
        </View>
      )}

      <LineChart
        data={chartData}
        width={Dimensions.get("window").width - 24}
        height={260}
        yAxisSuffix=" bpm"
        chartConfig={{
          backgroundGradientFrom: "#ffffff",
          backgroundGradientTo: "#ffffff",
          decimalPlaces: 0,
          color: (opacity = 1) => `rgba(0, 0, 0, ${opacity})`,
          labelColor: (opacity = 1) => `rgba(0, 0, 0, ${opacity})`,
        }}
        bezier
        style={styles.chart}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 12,
    justifyContent: "center",
  },
  title: {
    fontSize: 22,
    fontWeight: "700",
    marginBottom: 12,
  },
  debugBox: {
    padding: 10,
    marginBottom: 16,
    borderWidth: 1,
    borderRadius: 8,
  },
  error: {
    marginTop: 8,
    color: "red",
  },
  cards: {
    marginBottom: 20,
    gap: 8,
  },
  card: {
    fontSize: 18,
  },
  chart: {
    borderRadius: 12,
  },
});
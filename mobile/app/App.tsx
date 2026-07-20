import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import * as SecureStore from "expo-secure-store";
import * as ImagePicker from "expo-image-picker";
import { StatusBar } from "expo-status-bar";
import { LineChart, PieChart } from "react-native-chart-kit";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { SmartBackLogo } from "./SmartBackLogo";

type Role = "patient" | "doctor";
type User = { id: string; name: string; first_name?: string; last_name?: string; email: string; role: Role; patient_code?: string | null; professional_verified?: boolean; avatar_data?: string | null };
type Session = { access_token: string; user: User };
type DoctorPatient = User & { associated_at?: string; has_live_data: boolean };
type PostureStatus = "neutral" | "deviated" | "prolonged_deviation" | "marked_deviation";
type PostureSample = {
  timestamp: number; device_id: string; patient_id: string;
  pitch_deg: number; roll_deg: number; reference_pitch_deg: number; reference_roll_deg: number;
  deviation_deg: number; pitch_deviation_deg: number; roll_deviation_deg: number; deviation_duration_seconds: number;
  posture_status: PostureStatus; alert: string | null; threshold_profile: string;
};
type DeviceStatus = { device_id: string; state_of_charge?: number; charging?: boolean };
type AppScreen = "dashboard" | "profile" | "password" | "settings";
type HistorySample = { timestamp: string; deviation_deg: number; pitch_deviation_deg: number; roll_deviation_deg: number; posture_status: PostureStatus; is_incorrect: boolean };
type PatientStatistics = { samples: number; correct_percentage: number; incorrect_percentage: number; average_deviation_deg: number; maximum_deviation_deg: number };
type HistoryPeriod = 60 | 360 | 1440 | 10080;
type NightHistoryPeriod = 7 | 30 | 90 | 0;
type NightPosition = "supine" | "prone" | "right_side" | "left_side" | "unknown";
type NightSummary = {
  supine_seconds: number; prone_seconds: number; right_side_seconds: number;
  left_side_seconds: number; unknown_seconds: number; position_changes: number; data_gap_seconds: number;
};
type NightSession = {
  id: string; patient_id: string; device_id: string; status: "active" | "completed" | "interrupted";
  started_at: string; ended_at: string | null; duration_seconds: number; summary: NightSummary;
};
type NightStatus = { mode: "day" | "night"; active: boolean; session: NightSession | null };
type NightSample = {
  mode: "night"; timestamp: number; session_id: string; patient_id: string; device_id: string;
  position: NightPosition; candidate_position: NightPosition; confidence: number; data_gap_seconds: number;
};

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_URL = process.env.EXPO_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/wearable";
const SESSION_KEY = "smartback.session";
const THEME_KEY = "smartback.theme.dark";
const MAX_SAMPLES = 30;
const HISTORY_PERIODS: { minutes: HistoryPeriod; label: string }[] = [
  { minutes: 60, label: "1 ora" }, { minutes: 360, label: "6 ore" },
  { minutes: 1440, label: "24 ore" }, { minutes: 10080, label: "7 giorni" },
];
const NIGHT_POSITIONS: Record<NightPosition, { label: string; shortLabel: string; color: string }> = {
  supine: { label: "supino", shortLabel: "supino", color: "#3ec6ae" },
  prone: { label: "prono", shortLabel: "prono", color: "#ef8354" },
  right_side: { label: "decubito destro", shortLabel: "decubito destro", color: "#6f9ceb" },
  left_side: { label: "decubito sinistro", shortLabel: "decubito sinistro", color: "#b18be8" },
  unknown: { label: "transizione", shortLabel: "transizione", color: "#8da39d" },
};
const NAME_PATTERN = /^\p{L}+(?:[ '\u2019-]\p{L}+)*$/u;
const EMAIL_PATTERN = /^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}$/i;
const PASSWORD_NUMBER_PATTERN = /\d/;
const PASSWORD_SYMBOL_PATTERN = /[^\p{L}\p{N}\s]/u;
const FISCAL_CODE_PATTERN = /^[A-Z]{6}[0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{2}[A-Z][0-9LMNPQRSTUV]{3}[A-Z]$/;

const postureStyles: Record<PostureStatus, { label: string; detail: string; color: string; pale: string }> = {
  neutral: { label: "Postura neutra", detail: "Posizione vicina al riferimento calibrato.", color: "#087f6a", pale: "#dcf5ef" },
  deviated: { label: "Deviazione rilevata", detail: "È iniziato uno scostamento dal riferimento.", color: "#a15c00", pale: "#fff1d6" },
  prolonged_deviation: { label: "Deviazione prolungata", detail: "Lo scostamento persiste: correggi la posizione.", color: "#b54708", pale: "#ffead5" },
  marked_deviation: { label: "Deviazione marcata", detail: "Torna gradualmente alla postura di riferimento.", color: "#b42318", pale: "#fee4e2" },
};

const ThemeContext = createContext({ dark: false, setDark: (_value: boolean) => undefined as void });
function useAppTheme() { return useContext(ThemeContext); }

async function saveSession(session: Session | null) {
  if (session) await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(session));
  else await SecureStore.deleteItemAsync(SESSION_KEY);
}

async function api<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(payload?.detail ?? `Errore HTTP ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export default function App() {
  const [dark, setDarkState] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(THEME_KEY).then((stored) => setDarkState(stored === "true")).catch(() => undefined);
  }, []);

  function setDark(value: boolean) {
    setDarkState(value);
    SecureStore.setItemAsync(THEME_KEY, String(value)).catch(() => undefined);
  }

  return <SafeAreaProvider><ThemeContext.Provider value={{ dark, setDark }}><AppContent /></ThemeContext.Provider></SafeAreaProvider>;
}

function AppContent() {
  const [session, setSession] = useState<Session | null>(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    SecureStore.getItemAsync(SESSION_KEY)
      .then((stored) => stored && setSession(JSON.parse(stored)))
      .catch(() => undefined)
      .finally(() => setRestoring(false));
  }, []);

  async function authenticated(next: Session) {
    await saveSession(next);
    setSession(next);
  }

  async function logout() {
    if (session) api("/api/v1/auth/logout", { method: "POST" }, session.access_token).catch(() => undefined);
    await saveSession(null);
    setSession(null);
  }

  if (restoring) return <LoadingScreen />;
  if (!session) return <AuthScreen onAuthenticated={authenticated} />;
  return <Dashboard session={session} onSessionUpdate={authenticated} onLogout={logout} />;
}

function LoadingScreen() {
  const { dark } = useAppTheme();
  return (
    <SafeAreaView style={[styles.centerScreen, dark && styles.screenDark]}>
      <StatusBar style={dark ? "light" : "dark"} />
      <Logo />
      <ActivityIndicator style={{ marginTop: 24 }} color="#087f6a" size="large" />
    </SafeAreaView>
  );
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
  const { dark } = useAppTheme();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [role, setRole] = useState<Role>("patient");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [fiscalCode, setFiscalCode] = useState("");
  const [medicalCode, setMedicalCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    const cleanFirstName = firstName.trim().replace(/\s+/g, " ");
    const cleanLastName = lastName.trim().replace(/\s+/g, " ");
    const cleanEmail = email.trim().toLowerCase();
    if (mode === "register" && (!cleanFirstName || !cleanLastName)) {
      setError("Nome e cognome sono entrambi obbligatori.");
      return;
    }
    if (!EMAIL_PATTERN.test(cleanEmail)) {
      setError("Inserisci un'email valida nel formato nome@provider.dominio.");
      return;
    }
    if (password.length < 8) {
      setError("La password deve contenere almeno 8 caratteri.");
      return;
    }
    if (mode === "register" && (!NAME_PATTERN.test(cleanFirstName) || !NAME_PATTERN.test(cleanLastName))) {
      setError("Nome e cognome devono contenere solo lettere, spazi e apostrofi.");
      return;
    }
    if (mode === "register" && role === "patient" && !isValidFiscalCode(fiscalCode)) {
      setError("Inserisci un codice fiscale italiano valido.");
      return;
    }
    if (mode === "register" && role === "doctor" && !medicalCode.trim()) {
      setError("Inserisci il codice medico di verifica.");
      return;
    }
    if (mode === "register" && (!PASSWORD_NUMBER_PATTERN.test(password) || !PASSWORD_SYMBOL_PATTERN.test(password))) {
      setError("La password deve contenere almeno un numero e un simbolo speciale.");
      return;
    }
    setBusy(true);
    try {
      const path = mode === "login" ? "/api/v1/auth/login" : "/api/v1/auth/register";
      const body = mode === "login" ? { email: cleanEmail, password } : {
        first_name: cleanFirstName,
        last_name: cleanLastName,
        email: cleanEmail,
        password,
        role,
        fiscal_code: role === "patient" ? fiscalCode.toUpperCase().replace(/\s/g, "") : null,
        medical_code: role === "doctor" ? medicalCode.trim() : null,
      };
      onAuthenticated(await api<Session>(path, { method: "POST", body: JSON.stringify(body) }));
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "Operazione non riuscita";
      if (mode === "register" && (detail === "Utente già registrato" || detail === "Email already registered")) {
        Alert.alert("Registrazione non riuscita", "Utente già registrato");
      } else {
        setError(detail);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={[styles.authSafe, dark && styles.screenDark]}>
      <StatusBar style={dark ? "light" : "dark"} />
      <KeyboardAvoidingView style={styles.authKeyboard} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.authContent} keyboardShouldPersistTaps="handled">
          <Logo large />
          <Text style={[styles.authClaim, dark && styles.mutedDark]}>La postura guidata dai dati</Text>
          <View style={[styles.authCard, dark && styles.surfaceDark]}>
            <Text style={[styles.authTitle, dark && styles.textDark]}>{mode === "login" ? "Bentornato" : "Crea il tuo profilo"}</Text>
            <Text style={[styles.authSubtitle, dark && styles.mutedDark]}>{mode === "login" ? "Accedi al monitoraggio posturale" : "Registrati con i tuoi dati"}</Text>

            {mode === "register" && (
              <>
                <Text style={styles.inputLabel}>TIPO DI PROFILO</Text>
                <View style={styles.roleRow}>
                  <RoleButton selected={role === "patient"} label="Paziente" onPress={() => setRole("patient")} />
                  <RoleButton selected={role === "doctor"} label="Medico" onPress={() => setRole("doctor")} />
                </View>
                <Field label="NOME" value={firstName} onChangeText={setFirstName} placeholder="Mario" autoCapitalize="words" />
                <Field label="COGNOME" value={lastName} onChangeText={setLastName} placeholder="Rossi" autoCapitalize="words" />
              </>
            )}
            <Field label="EMAIL" value={email} onChangeText={setEmail} placeholder="nome@email.it" keyboardType="email-address" autoCapitalize="none" />
            {mode === "register" && (role === "patient" ? (
              <Field key="fiscal-code" label="CODICE FISCALE" value={fiscalCode} onChangeText={setFiscalCode} placeholder="RSSMRA80A01H501U" autoCapitalize="characters" maxLength={16} editable={!busy} />
            ) : (
              <Field
                key="medical-code"
                label="CODICE MEDICO"
                value={medicalCode}
                onChangeText={setMedicalCode}
                placeholder="Inserisci il codice medico"
                autoCapitalize="characters"
                autoCorrect={false}
                editable={!busy}
              />
            ))}
            <Field label="PASSWORD" value={password} onChangeText={setPassword} placeholder="Almeno 8 caratteri" secureTextEntry autoCapitalize="none" />
            {error ? <Text style={styles.formError}>{error}</Text> : null}
            <Pressable onPress={submit} disabled={busy} style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}>
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>{mode === "login" ? "Accedi" : "Registrati"}</Text>}
            </Pressable>
            <Pressable onPress={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
              <Text style={styles.switchText}>
                {mode === "login" ? "Non hai un account?  " : "Hai già un account?  "}
                <Text style={styles.switchLink}>{mode === "login" ? "Registrati" : "Accedi"}</Text>
              </Text>
            </Pressable>
          </View>
          <Text style={styles.demoNote}>Non sostituisce una valutazione clinica</Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Dashboard({ session, onSessionUpdate, onLogout }: { session: Session; onSessionUpdate: (session: Session) => void; onLogout: () => void }) {
  const { dark, setDark } = useAppTheme();
  const { width } = useWindowDimensions();
  const [screen, setScreen] = useState<AppScreen>("dashboard");
  const [samples, setSamples] = useState<PostureSample[]>([]);
  const [device, setDevice] = useState<DeviceStatus | null>(null);
  const [message, setMessage] = useState("");
  const [doctorPatients, setDoctorPatients] = useState<DoctorPatient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<DoctorPatient | null>(null);
  const [patientsLoading, setPatientsLoading] = useState(session.user.role === "doctor");
  const [nightStatus, setNightStatus] = useState<NightStatus | null>(null);
  const [nightSample, setNightSample] = useState<NightSample | null>(null);
  const [nightBusy, setNightBusy] = useState(false);
  const [nightError, setNightError] = useState("");
  const [nightClock, setNightClock] = useState(Date.now());
  const [nightStatusSyncedAt, setNightStatusSyncedAt] = useState(Date.now());
  const [nightPositionSince, setNightPositionSince] = useState(Date.now());
  const nightActiveRef = useRef(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const visibleSamples = session.user.role === "doctor"
    ? samples.filter((sample) => sample.patient_id === selectedPatient?.patient_code)
    : samples;
  const latest = visibleSamples[visibleSamples.length - 1];
  const posture = latest ? postureStyles[latest.posture_status] : null;
  const monitoredUser = session.user.role === "doctor" ? selectedPatient : session.user;
  const monitoredDeviceId = latest?.device_id ?? nightStatus?.session?.device_id ?? null;
  const monitoredBattery = monitoredDeviceId && device?.device_id === monitoredDeviceId && device.state_of_charge != null
    ? Math.round(device.state_of_charge)
    : null;

  const refreshDevice = useCallback(async () => {
    try { setDevice(await api<DeviceStatus>("/api/v1/device/latest")); } catch { /* optional */ }
  }, []);

  useEffect(() => {
    refreshDevice();
    const interval = setInterval(refreshDevice, 15000);
    return () => clearInterval(interval);
  }, [refreshDevice]);

  const loadDoctorPatients = useCallback(async () => {
    if (session.user.role !== "doctor") return;
    setPatientsLoading(true);
    try {
      const response = await api<{ items: DoctorPatient[] }>("/api/v1/doctor/patients", {}, session.access_token);
      setDoctorPatients(response.items);
      setSelectedPatient((current) => current ? response.items.find((patient) => patient.id === current.id) ?? null : null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Impossibile caricare i pazienti");
    } finally {
      setPatientsLoading(false);
    }
  }, [session.access_token, session.user.role]);

  useEffect(() => { loadDoctorPatients(); }, [loadDoctorPatients]);

  const loadNightStatus = useCallback(async () => {
    if (session.user.role === "doctor" && !selectedPatient) {
      setNightStatus(null);
      setNightSample(null);
      return;
    }
    try {
      const patientQuery = session.user.role === "doctor" ? `?patient_id=${encodeURIComponent(selectedPatient!.id)}` : "";
      const response = await api<NightStatus>(`/api/v1/night-monitoring/status${patientQuery}`, {}, session.access_token);
      setNightStatus(response);
      setNightStatusSyncedAt(Date.now());
      if (session.user.role === "patient" && nightActiveRef.current && !response.active) setDark(false);
      nightActiveRef.current = response.active;
      setNightError("");
      if (!response.active) setNightSample(null);
    } catch (caught) {
      setNightError(caught instanceof Error ? caught.message : "Impossibile verificare la modalità notte.");
    }
  }, [selectedPatient, session.access_token, session.user.role, setDark]);

  useEffect(() => {
    loadNightStatus();
    const interval = setInterval(loadNightStatus, 5000);
    return () => clearInterval(interval);
  }, [loadNightStatus]);

  useEffect(() => {
    if (session.user.role === "patient" && nightStatus?.active && !dark) setDark(true);
  }, [dark, nightStatus?.active, session.user.role, setDark]);

  useEffect(() => {
    if (!nightStatus?.active) return;
    setNightClock(Date.now());
    const interval = setInterval(() => setNightClock(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [nightStatus?.active]);

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    function connect() {
      if (!active) return;
      socket = new WebSocket(WS_URL);
      socket.onopen = () => { if (active) setMessage(""); };
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as PostureSample | NightSample;
          if ("mode" in payload && payload.mode === "night") {
            const monitoredPatientCode = session.user.role === "doctor" ? selectedPatient?.patient_code : session.user.patient_code;
            if (payload.patient_id === monitoredPatientCode) {
              setNightSample((current) => {
                if (current?.position !== payload.position) setNightPositionSince(Date.now());
                return payload;
              });
            }
          } else if ("deviation_deg" in payload && typeof payload.deviation_deg === "number") {
            setSamples((current) => [...current.slice(-(MAX_SAMPLES - 1)), payload]);
          }
        } catch { setMessage("Dato ricevuto non valido."); }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (!active) return;
        setMessage("Connessione in pausa. Riprovo automaticamente…");
        reconnectTimer.current = setTimeout(connect, 3000);
      };
    }
    connect();
    return () => { active = false; if (reconnectTimer.current) clearTimeout(reconnectTimer.current); socket?.close(); };
  }, [selectedPatient?.patient_code, session.user.patient_code, session.user.role]);

  async function toggleNightMode() {
    if (session.user.role !== "patient" || nightBusy) return;
    const stopping = Boolean(nightStatus?.active);
    setNightBusy(true); setNightError("");
    try {
      const response = await api<NightStatus>(
        stopping ? "/api/v1/night-monitoring/stop" : "/api/v1/night-monitoring/start",
        { method: "POST" }, session.access_token,
      );
      setNightStatus(response);
      setNightStatusSyncedAt(Date.now());
      nightActiveRef.current = response.active;
      if (response.active) setDark(true);
      else { setDark(false); setNightSample(null); }
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "Operazione non riuscita.";
      setNightError(detail);
      Alert.alert(stopping ? "Arresto non riuscito" : "Attivazione non riuscita", detail);
    } finally {
      setNightBusy(false);
    }
  }

  const roleLabel = session.user.role === "doctor" ? "Medico" : "Paziente";

  return (
    <SafeAreaView edges={["top", "left", "right"]} style={[styles.dashboardSafe, dark && styles.screenDark]}>
      <StatusBar style={dark ? "light" : "dark"} />
      <View style={[styles.fixedHeader, dark && styles.headerDark]}>
        <Pressable onPress={() => setScreen("dashboard")}><Text style={styles.headerBrandSmart}>Smart<Text style={styles.headerBrandBack}>Back</Text></Text></Pressable>
        <View style={styles.headerRight}>
          <Pressable accessibilityLabel="Apri il profilo" onPress={() => setScreen("profile")} style={[styles.avatar, screen === "profile" && styles.avatarSelected]}><UserAvatar user={session.user} size={34} /></Pressable>
        </View>
      </View>

      {screen === "profile" ? (
        <ProfileScreen session={session} onSessionUpdate={onSessionUpdate} onBack={() => setScreen("dashboard")} onPassword={() => setScreen("password")} onSettings={() => setScreen("settings")} onLogout={onLogout} />
      ) : screen === "password" ? (
        <ChangePasswordScreen token={session.access_token} onBack={() => setScreen("profile")} />
      ) : screen === "settings" ? (
        <SettingsScreen nightModeActive={Boolean(nightStatus?.active)} onBack={() => setScreen("profile")} />
      ) : (
      <ScrollView style={dark && styles.screenDark} contentContainerStyle={styles.dashboardContent}>
        <View>
          <Text style={[styles.welcome, dark && styles.textDark]}>Ciao, {session.user.name.split(" ")[0]}</Text>
          <Text style={[styles.roleCaption, dark && styles.mutedDark]}>{roleLabel} · {session.user.role === "doctor" ? "Consulta i pazienti associati" : "Il tuo monitoraggio posturale"}</Text>
        </View>
        {session.user.role === "patient" && <PatientDeviceSummary deviceId={monitoredDeviceId} battery={monitoredBattery} />}
        {session.user.role === "patient" && <MonitoringSectionHeader mode="day" title="Monitoraggio diurno" subtitle="Stato attuale e percentuali dello storico posturale" />}

        {session.user.role === "doctor" && !selectedPatient ? (
          <DoctorPatientDirectory
            patients={doctorPatients}
            loading={patientsLoading}
            onSelect={setSelectedPatient}
          />
        ) : !latest || !posture ? (
          <>
            {session.user.role === "doctor" && <Pressable onPress={() => setSelectedPatient(null)} style={styles.patientStrip}><Text style={styles.backArrow}>‹</Text><View style={{ flex: 1 }}><Text style={styles.overline}>PAZIENTE SELEZIONATO</Text><Text style={styles.patientName}>{selectedPatient?.name}</Text></View><Text style={styles.patientCode}>{selectedPatient?.patient_code}</Text></Pressable>}
            {session.user.role === "doctor" && <PatientDeviceSummary deviceId={monitoredDeviceId} battery={monitoredBattery} />}
            {session.user.role === "doctor" && <MonitoringSectionHeader mode="day" title="Monitoraggio diurno" subtitle="Dati posturali in tempo reale e storico completo" />}
            <View style={[styles.waitingCard, dark && styles.surfaceDark]}><ActivityIndicator color="#087f6a" size="large" /><Text style={[styles.waitingTitle, dark && styles.textDark]}>Nessun dato in tempo reale</Text><Text style={[styles.muted, dark && styles.mutedDark]}>Questo paziente non ha ancora un dispositivo attivo.</Text></View>
            <HistoricalInsights session={session} patient={selectedPatient} />
            {session.user.role === "patient" && <PatientNightSection status={nightStatus} sample={nightSample} clock={nightClock} statusSyncedAt={nightStatusSyncedAt} positionSince={nightPositionSince} busy={nightBusy} error={nightError} onToggle={toggleNightMode} />}
            {session.user.role === "doctor" && selectedPatient && <DoctorNightSection session={session} patient={selectedPatient} status={nightStatus} sample={nightSample} clock={nightClock} statusSyncedAt={nightStatusSyncedAt} positionSince={nightPositionSince} error={nightError} />}
          </>
        ) : (
          <>
            {session.user.role === "doctor" && (
              <Pressable onPress={() => setSelectedPatient(null)} style={styles.patientStrip}><Text style={styles.backArrow}>‹</Text><View style={{ flex: 1 }}><Text style={styles.overline}>PAZIENTE SELEZIONATO</Text><Text style={styles.patientName}>{selectedPatient?.name}</Text></View><Text style={styles.patientCode}>{selectedPatient?.patient_code}</Text></Pressable>
            )}
            {session.user.role === "doctor" && <PatientDeviceSummary deviceId={monitoredDeviceId} battery={monitoredBattery} />}
            {session.user.role === "doctor" && <MonitoringSectionHeader mode="day" title="Monitoraggio diurno" subtitle="Dati posturali in tempo reale e storico completo" />}
            <View style={[styles.postureCard, { backgroundColor: posture.pale }]}>
              <View style={styles.postureTop}><UserAvatar user={monitoredUser} size={43} accentColor={posture.color} /><View style={{ flex: 1 }}><Text style={[styles.postureLabel, { color: posture.color }]}>{posture.label}</Text><Text style={styles.postureDetail}>{posture.detail}</Text></View></View>
              <View style={styles.deviationRow}><Text style={styles.deviationCaption}>DEVIAZIONE DAL RIFERIMENTO</Text><Text style={[styles.deviationValue, { color: posture.color }]}>{formatSigned(latest.deviation_deg)}</Text></View>
            </View>
            <View style={styles.metricsRow}>
              <Metric label="Pitch" value={formatSigned(latest.pitch_deg)} />
              <Metric label="Roll" value={formatSigned(latest.roll_deg)} />
              <Metric label="Durata" value={`${latest.deviation_duration_seconds.toFixed(0)} s`} />
            </View>
            <CalibrationSummary pitch={latest.reference_pitch_deg} roll={latest.reference_roll_deg} />
            <LiveAxisChart title="Pitch in tempo reale" samples={visibleSamples} valueField="pitch_deg" referenceField="reference_pitch_deg" color="#315f9a" referenceColor="#1e40af" width={Math.max(280, width - 56)} />
            <LiveAxisChart title="Roll in tempo reale" samples={visibleSamples} valueField="roll_deg" referenceField="reference_roll_deg" color="#8b5fbf" referenceColor="#d94f9b" width={Math.max(280, width - 56)} />
            <HistoricalInsights session={session} patient={selectedPatient} />
            {session.user.role === "patient" && <PatientNightSection status={nightStatus} sample={nightSample} clock={nightClock} statusSyncedAt={nightStatusSyncedAt} positionSince={nightPositionSince} busy={nightBusy} error={nightError} onToggle={toggleNightMode} />}
            {session.user.role === "doctor" && selectedPatient && <DoctorNightSection session={session} patient={selectedPatient} status={nightStatus} sample={nightSample} clock={nightClock} statusSyncedAt={nightStatusSyncedAt} positionSince={nightPositionSince} error={nightError} />}
          </>
        )}
        {message ? <Text style={styles.message}>{message}</Text> : null}
        {session.user.role === "patient" && <Text style={styles.disclaimer}>Soglie dimostrative, non validate per uso clinico.</Text>}
      </ScrollView>
      )}
    </SafeAreaView>
  );
}

function NightModePanel({ status, sample, clock, statusSyncedAt, positionSince, busy, error, onToggle, readOnly = false }: { status: NightStatus | null; sample: NightSample | null; clock: number; statusSyncedAt: number; positionSince: number; busy: boolean; error: string; onToggle: () => void; readOnly?: boolean }) {
  const { dark } = useAppTheme();
  const { width } = useWindowDimensions();
  const active = Boolean(status?.active);
  const position = NIGHT_POSITIONS[sample?.position ?? "unknown"];
  const summary = status?.session?.summary;
  const liveSeconds = (target: NightPosition, stored: number) => stored + (
    sample?.position === target
      ? Math.max(0, (clock - Math.max(statusSyncedAt, positionSince)) / 1000)
      : 0
  );
  const sessionDuration = status?.session?.started_at
    ? Math.max(0, (clock - Date.parse(status.session.started_at)) / 1000)
    : 0;
  const nightPositionSeconds = [
    { name: "supino", seconds: liveSeconds("supine", summary?.supine_seconds ?? 0), color: NIGHT_POSITIONS.supine.color },
    { name: "prono", seconds: liveSeconds("prone", summary?.prone_seconds ?? 0), color: NIGHT_POSITIONS.prone.color },
    { name: "decubito destro", seconds: liveSeconds("right_side", summary?.right_side_seconds ?? 0), color: NIGHT_POSITIONS.right_side.color },
    { name: "decubito sinistro", seconds: liveSeconds("left_side", summary?.left_side_seconds ?? 0), color: NIGHT_POSITIONS.left_side.color },
  ];
  const classifiedSeconds = nightPositionSeconds.reduce((total, item) => total + item.seconds, 0);
  const nightPieData = nightPositionSeconds.map((item) => ({
    name: item.name,
    percentage: classifiedSeconds > 0 ? Math.round(item.seconds / classifiedSeconds * 100) : 0,
    color: item.color,
    legendFontColor: dark ? "#d5e4f5" : "#263b57",
    legendFontSize: 10,
  }));
  return (
    <View style={[styles.nightCard, active && styles.nightCardActive, dark && styles.nightCardDark]}>
      <View style={styles.nightHeader}>
        <View style={styles.nightMoon}><Text style={styles.nightMoonText}>☾</Text></View>
        <View style={{ flex: 1 }}><Text style={styles.nightTitle}>Modalità notte</Text><Text style={styles.nightSubtitle}>{active ? "Monitoraggio notturno in corso" : "Rileva la posizione durante il riposo"}</Text></View>
        {active && <View style={styles.nightLiveBadge}><View style={styles.nightLiveDot} /><Text style={styles.nightLiveText}>LIVE</Text></View>}
      </View>
      {active ? (
        <>
          <View style={styles.nightPositionBox}>
            <Text style={styles.nightOverline}>POSIZIONE ATTUALE</Text>
            <Text style={[styles.nightPosition, { color: position.color }]}>{position.label}</Text>
            {!sample && <Text style={styles.nightWaitingText}>In attesa del primo dato…</Text>}
          </View>
          <View style={styles.nightStatsGrid}>
            <NightStat label="supino" seconds={liveSeconds("supine", summary?.supine_seconds ?? 0)} color={NIGHT_POSITIONS.supine.color} />
            <NightStat label="prono" seconds={liveSeconds("prone", summary?.prone_seconds ?? 0)} color={NIGHT_POSITIONS.prone.color} />
            <NightStat label="decubito destro" seconds={liveSeconds("right_side", summary?.right_side_seconds ?? 0)} color={NIGHT_POSITIONS.right_side.color} />
            <NightStat label="decubito sinistro" seconds={liveSeconds("left_side", summary?.left_side_seconds ?? 0)} color={NIGHT_POSITIONS.left_side.color} />
          </View>
          {!readOnly && <View style={styles.nightPieCard}><Text style={styles.nightOverline}>DISTRIBUZIONE PERCENTUALE</Text>{classifiedSeconds > 0 ? <PieChart data={nightPieData} width={Math.max(270, width - 72)} height={160} accessor="percentage" backgroundColor="transparent" paddingLeft="5" style={styles.nightPieChart} chartConfig={{ color: (opacity = 1) => `rgba(255,255,255,${opacity})` }} /> : <Text style={styles.nightPieEmpty}>Il grafico apparirà dopo i primi dati classificati.</Text>}</View>}
          <View style={styles.nightMeta}><Text style={styles.nightMetaText}>Maglia: {status?.session?.device_id ?? "—"}</Text><Text style={styles.nightMetaText}>Durata: {formatDuration(sessionDuration)}</Text></View>
        </>
      ) : <Text style={styles.nightDescription}>{readOnly ? "La modalità notte non è attiva. Il pannello mostrerà automaticamente i dati quando il paziente avvierà il monitoraggio." : "Attivando questa modalità il tema scuro si abilita automaticamente e i dati vengono inviati alla vista notturna dedicata."}</Text>}
      {error ? <Text style={styles.nightError}>{error}</Text> : null}
      {!readOnly && <Pressable disabled={busy || !status} onPress={onToggle} style={({ pressed }) => [styles.nightButton, active && styles.nightStopButton, pressed && styles.pressed]}>
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.nightButtonText}>{active ? "TERMINA MODALITÀ NOTTE" : "MODALITÀ NOTTE"}</Text>}
      </Pressable>}
    </View>
  );
}

function NightStat({ label, seconds, color }: { label: string; seconds: number; color: string }) {
  return <View style={styles.nightStat}><View style={[styles.nightStatDot, { backgroundColor: color }]} /><Text style={styles.nightStatValue}>{formatDuration(seconds)}</Text><Text style={styles.nightStatLabel}>{label}</Text></View>;
}

function MonitoringSectionHeader({ mode, title, subtitle }: { mode: "day" | "night"; title: string; subtitle: string }) {
  const { dark } = useAppTheme();
  const night = mode === "night";
  return (
    <View style={[styles.monitoringSectionHeader, night ? styles.monitoringSectionNight : styles.monitoringSectionDay, dark && styles.monitoringSectionHeaderDark]}>
      <View style={[styles.monitoringSectionIcon, night ? styles.monitoringSectionIconNight : styles.monitoringSectionIconDay]}><Text style={styles.monitoringSectionIconText}>{night ? "☾" : "☀"}</Text></View>
      <View style={{ flex: 1 }}><Text style={[styles.monitoringSectionTitle, dark && styles.textDark]}>{title}</Text><Text style={[styles.monitoringSectionSubtitle, dark && styles.mutedDark]}>{subtitle}</Text></View>
    </View>
  );
}

function PatientNightSection({ status, sample, clock, statusSyncedAt, positionSince, busy, error, onToggle }: { status: NightStatus | null; sample: NightSample | null; clock: number; statusSyncedAt: number; positionSince: number; busy: boolean; error: string; onToggle: () => void }) {
  return <View style={styles.doctorNightSection}><MonitoringSectionHeader mode="night" title="Monitoraggio notturno" subtitle="Attivazione, posizione corrente e percentuali della sessione" /><NightModePanel status={status} sample={sample} clock={clock} statusSyncedAt={statusSyncedAt} positionSince={positionSince} busy={busy} error={error} onToggle={onToggle} /></View>;
}

function DoctorNightSection({ session, patient, status, sample, clock, statusSyncedAt, positionSince, error }: { session: Session; patient: DoctorPatient; status: NightStatus | null; sample: NightSample | null; clock: number; statusSyncedAt: number; positionSince: number; error: string }) {
  return (
    <View style={styles.doctorNightSection}>
      <MonitoringSectionHeader mode="night" title="Monitoraggio notturno" subtitle="Stato live e storico delle sessioni del paziente" />
      <NightModePanel status={status} sample={sample} clock={clock} statusSyncedAt={statusSyncedAt} positionSince={positionSince} busy={false} error={error} onToggle={() => undefined} readOnly />
      <NightHistoryPanel session={session} patient={patient} refreshKey={`${status?.session?.id ?? "none"}:${status?.active ?? false}`} />
    </View>
  );
}

function NightHistoryPanel({ session, patient, refreshKey }: { session: Session; patient: DoctorPatient; refreshKey: string }) {
  const { dark } = useAppTheme();
  const [period, setPeriod] = useState<NightHistoryPeriod>(30);
  const [sessions, setSessions] = useState<NightSession[]>([]);
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [sessionMenuOpen, setSessionMenuOpen] = useState(false);
  const [sessionSearch, setSessionSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadHistory = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const response = await api<{ items: NightSession[] }>(`/api/v1/night-monitoring/history?patient_id=${encodeURIComponent(patient.id)}&limit=200`, {}, session.access_token);
      setSessions(response.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Impossibile caricare lo storico notturno.");
    } finally {
      setLoading(false);
    }
  }, [patient.id, refreshKey, session.access_token]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const visibleSessions = useMemo(() => {
    if (period === 0) return sessions;
    const cutoff = Date.now() - period * 24 * 60 * 60 * 1000;
    return sessions.filter((item) => Date.parse(item.started_at) >= cutoff);
  }, [period, sessions]);

  const selectedSession = selectedSessionId ? sessions.find((item) => item.id === selectedSessionId) ?? null : null;
  const normalizedSearch = sessionSearch.trim().toLocaleLowerCase("it-IT");
  const searchableSessions = sessions.filter((item) => {
    if (!normalizedSearch) return true;
    const date = new Date(item.started_at);
    const searchableDate = `${date.toLocaleDateString("it-IT")} ${date.toLocaleDateString("it-IT", { day: "2-digit", month: "long", year: "numeric" })} ${date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`.toLocaleLowerCase("it-IT");
    return searchableDate.includes(normalizedSearch);
  });
  const histogramSessions = selectedSession ? [selectedSession] : visibleSessions;
  const combinedSummary = histogramSessions.reduce<NightSummary>((total, item) => ({
    supine_seconds: total.supine_seconds + item.summary.supine_seconds,
    prone_seconds: total.prone_seconds + item.summary.prone_seconds,
    right_side_seconds: total.right_side_seconds + item.summary.right_side_seconds,
    left_side_seconds: total.left_side_seconds + item.summary.left_side_seconds,
    unknown_seconds: total.unknown_seconds + item.summary.unknown_seconds,
    position_changes: total.position_changes + item.summary.position_changes,
    data_gap_seconds: total.data_gap_seconds + item.summary.data_gap_seconds,
  }), { supine_seconds: 0, prone_seconds: 0, right_side_seconds: 0, left_side_seconds: 0, unknown_seconds: 0, position_changes: 0, data_gap_seconds: 0 });
  const classifiedTotal = combinedSummary.supine_seconds + combinedSummary.prone_seconds + combinedSummary.right_side_seconds + combinedSummary.left_side_seconds;
  const histogramBars = [
    { label: "supino", value: combinedSummary.supine_seconds, color: NIGHT_POSITIONS.supine.color },
    { label: "prono", value: combinedSummary.prone_seconds, color: NIGHT_POSITIONS.prone.color },
    { label: "decubito\ndestro", value: combinedSummary.right_side_seconds, color: NIGHT_POSITIONS.right_side.color },
    { label: "decubito\nsinistro", value: combinedSummary.left_side_seconds, color: NIGHT_POSITIONS.left_side.color },
  ].map((bar) => ({ ...bar, percentage: classifiedTotal > 0 ? Math.round(bar.value / classifiedTotal * 100) : 0 }));
  const selectedLabel = selectedSession ? formatNightSessionLabel(selectedSession) : "Tutte le sessioni nel periodo";

  return (
    <View style={[styles.nightHistoryCard, dark && styles.surfaceDark]}>
      <View style={styles.historyHeading}><View><Text style={[styles.sectionTitle, dark && styles.textDark]}>Storico notturno</Text><Text style={[styles.mutedSmall, dark && styles.mutedDark]}>Tutte le sessioni nella finestra selezionata</Text></View>{loading && <ActivityIndicator color="#6f9ceb" size="small" />}</View>
      <View style={styles.periodRow}>{([{ value: 7, label: "7 giorni" }, { value: 30, label: "30 giorni" }, { value: 90, label: "90 giorni" }, { value: 0, label: "Tutto" }] as { value: NightHistoryPeriod; label: string }[]).map((option) => <Pressable key={option.value} onPress={() => { setPeriod(option.value); setSelectedSessionId(null); }} style={[styles.periodButton, styles.nightPeriodButton, period === option.value && !selectedSessionId && styles.nightPeriodButtonSelected]}><Text style={[styles.periodText, period === option.value && !selectedSessionId && styles.periodTextSelected]}>{option.label}</Text></Pressable>)}</View>
      <View style={styles.sessionSelectorWrap}>
        <Text style={[styles.inputLabel, dark && styles.mutedDark]}>SESSIONE NOTTURNA</Text>
        <Pressable accessibilityLabel="Seleziona sessione notturna" onPress={() => setSessionMenuOpen((current) => !current)} style={[styles.sessionSelector, dark && styles.surfaceDarkAlt]}><Text numberOfLines={1} style={[styles.sessionSelectorText, dark && styles.textDark]}>{selectedLabel}</Text><Text style={styles.sessionSelectorChevron}>{sessionMenuOpen ? "⌃" : "⌄"}</Text></Pressable>
        {sessionMenuOpen && <View style={[styles.sessionDropdown, dark && styles.surfaceDarkAlt]}>
          <TextInput value={sessionSearch} onChangeText={setSessionSearch} placeholder="Cerca per data, es. 20/07/2026" placeholderTextColor={dark ? "#7f9a93" : "#98aaa5"} style={[styles.sessionSearchInput, dark && styles.inputDark]} />
          <Pressable onPress={() => { setSelectedSessionId(null); setSessionMenuOpen(false); setSessionSearch(""); }} style={styles.sessionOption}><Text style={[styles.sessionOptionTitle, dark && styles.textDark]}>Tutte le sessioni nel periodo</Text><Text style={[styles.sessionOptionMeta, dark && styles.mutedDark]}>{visibleSessions.length} sessioni disponibili</Text></Pressable>
          <ScrollView nestedScrollEnabled style={styles.sessionOptionsScroll}>
            {searchableSessions.map((item) => <Pressable key={item.id} onPress={() => { setSelectedSessionId(item.id); setSessionMenuOpen(false); setSessionSearch(""); }} style={[styles.sessionOption, selectedSessionId === item.id && styles.sessionOptionSelected]}><Text style={[styles.sessionOptionTitle, dark && styles.textDark]}>{formatNightSessionLabel(item)}</Text><Text style={[styles.sessionOptionMeta, dark && styles.mutedDark]}>{formatDuration(item.duration_seconds)} · {item.status === "active" ? "in corso" : "completata"}</Text></Pressable>)}
            {searchableSessions.length === 0 && <Text style={styles.sessionSearchEmpty}>Nessuna sessione corrisponde alla data cercata.</Text>}
          </ScrollView>
        </View>}
      </View>
      <View style={styles.nightHistogram}><View style={styles.histogramGuideTop}><Text style={styles.histogramGuideText}>100%</Text></View><View style={styles.histogramGuideMiddle}><Text style={styles.histogramGuideText}>50%</Text></View><View style={styles.histogramBars}>{histogramBars.map((bar) => <View key={bar.label} style={styles.histogramColumn}><Text style={[styles.histogramValue, dark && styles.textDark]}>{bar.percentage}%</Text><View style={styles.histogramTrack}><View style={[styles.histogramBar, { height: Math.max(3, bar.percentage * 1.5), backgroundColor: bar.color }]} /></View><Text style={[styles.histogramLabel, dark && styles.mutedDark]}>{bar.label}</Text></View>)}</View></View>
      <Text style={[styles.nightChartCaption, dark && styles.mutedDark]}>{selectedSession ? `Percentuali della sessione selezionata · ${formatNightSessionLabel(selectedSession)}` : `${visibleSessions.length} ${visibleSessions.length === 1 ? "sessione inclusa" : "sessioni incluse"} nel periodo selezionato`}</Text>
      {!loading && histogramSessions.length === 0 && <Text style={styles.nightHistoryEmpty}>Nessuna sessione notturna nel periodo selezionato.</Text>}
      {error ? <Text style={styles.formError}>{error}</Text> : null}
    </View>
  );
}

function HistoricalInsights({ session, patient }: { session: Session; patient: DoctorPatient | null }) {
  const { dark } = useAppTheme();
  const { width } = useWindowDimensions();
  const [period, setPeriod] = useState<HistoryPeriod>(60);
  const [history, setHistory] = useState<HistorySample[]>([]);
  const [statistics, setStatistics] = useState<PatientStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const patientId = session.user.role === "doctor" ? patient?.id : undefined;

  const loadHistory = useCallback(async () => {
    if (session.user.role === "doctor" && !patientId) return;
    setLoading(true); setError("");
    const patientQuery = patientId ? `&patient_id=${encodeURIComponent(patientId)}` : "";
    try {
      const requests: [Promise<{ items: HistorySample[] }>, Promise<PatientStatistics | null>] = [
        api(`/api/v1/posture/history?minutes=${period}${patientQuery}`, {}, session.access_token),
        session.user.role === "patient"
          ? api<PatientStatistics>(`/api/v1/patient/statistics?minutes=${period}`, {}, session.access_token)
          : Promise.resolve(null),
      ];
      const [historyResponse, statisticsResponse] = await Promise.all(requests);
      setHistory(historyResponse.items);
      setStatistics(statisticsResponse);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Impossibile caricare lo storico.");
    } finally {
      setLoading(false);
    }
  }, [patientId, period, session.access_token, session.user.role]);

  useEffect(() => { loadHistory(); }, [loadHistory]);

  const chartSamples: HistorySample[] = history.length ? history : [{ timestamp: new Date().toISOString(), deviation_deg: 0, pitch_deviation_deg: 0, roll_deviation_deg: 0, posture_status: "neutral", is_incorrect: false }];

  return (
    <>
      <View style={[styles.historyCard, dark && styles.surfaceDark]}>
        <View style={styles.historyHeading}><View><Text style={[styles.sectionTitle, dark && styles.textDark]}>Storico diurno</Text><Text style={[styles.mutedSmall, dark && styles.mutedDark]}>{session.user.role === "patient" ? "Percentuali e deviazioni nel periodo selezionato" : "Deviazioni pitch e roll nell'intera finestra selezionata"}</Text></View>{loading && <ActivityIndicator color="#087f6a" size="small" />}</View>
        <View style={styles.periodRow}>{HISTORY_PERIODS.map((option) => <Pressable key={option.minutes} onPress={() => setPeriod(option.minutes)} style={[styles.periodButton, period === option.minutes && styles.periodButtonSelected]}><Text style={[styles.periodText, period === option.minutes && styles.periodTextSelected]}>{option.label}</Text></Pressable>)}</View>
        {session.user.role === "patient" && statistics && <View style={styles.patientHistoryPercentages}><Statistic label="Postura corretta" value={`${statistics.correct_percentage}%`} color="#087f6a" /><Statistic label="Postura scorretta" value={`${statistics.incorrect_percentage}%`} color="#d92d20" /></View>}
        <HistoryAxisChart title="Deviazione pitch" samples={chartSamples} period={period} field="pitch_deviation_deg" color="#315f9a" width={Math.max(280, width - 56)} />
        <HistoryAxisChart title="Deviazione roll" samples={chartSamples} period={period} field="roll_deviation_deg" color="#8b5fbf" width={Math.max(280, width - 56)} />
        {!loading && history.length === 0 && <Text style={styles.noHistoryText}>Nessun dato disponibile nel periodo selezionato.</Text>}
        {error ? <Text style={styles.formError}>{error}</Text> : null}
      </View>

    </>
  );
}

function CalibrationSummary({ pitch, roll }: { pitch: number; roll: number }) {
  const { dark } = useAppTheme();
  return <View><Text style={[styles.calibrationHeading, dark && styles.textDark]}>Valori di calibrazione</Text><View style={styles.calibrationRow}><View style={[styles.calibrationCard, dark && styles.surfaceDark]}><Text style={[styles.calibrationLabel, dark && styles.mutedDark]}>RIFERIMENTO PITCH</Text><Text style={[styles.calibrationValue, styles.pitchCalibrationValue]}>{formatSigned(pitch)}</Text></View><View style={[styles.calibrationCard, dark && styles.surfaceDark]}><Text style={[styles.calibrationLabel, dark && styles.mutedDark]}>RIFERIMENTO ROLL</Text><Text style={[styles.calibrationValue, styles.rollCalibrationValue]}>{formatSigned(roll)}</Text></View></View></View>;
}

function LiveAxisChart({ title, samples, valueField, referenceField, color, referenceColor, width }: { title: string; samples: PostureSample[]; valueField: "pitch_deg" | "roll_deg"; referenceField: "reference_pitch_deg" | "reference_roll_deg"; color: string; referenceColor: string; width: number }) {
  const { dark } = useAppTheme();
  const reference = samples.length ? samples[samples.length - 1][referenceField] : 0;
  const chartPointCount = Math.max(samples.length, 1);
  const data = {
    labels: samples.length ? samples.map((_, index) => index === 0 || index === samples.length - 1 ? `${index + 1}` : "") : [""],
    datasets: [
      { data: samples.length ? samples.map((sample) => sample[valueField]) : [0], color: () => color, strokeWidth: 3 },
      { data: Array(chartPointCount).fill(reference), color: () => referenceColor, strokeWidth: 2, strokeDashArray: [7, 6] },
      { data: Array(chartPointCount).fill(30), color: () => "rgba(0,0,0,0)", strokeWidth: 1, withDots: false },
      { data: Array(chartPointCount).fill(-30), color: () => "rgba(0,0,0,0)", strokeWidth: 1, withDots: false },
    ],
  };
  return <View style={[styles.whiteCard, dark && styles.surfaceDark]}><View style={styles.sectionHeading}><View style={styles.liveChartHeading}><Text style={[styles.sectionTitle, dark && styles.textDark]}>{title}</Text><Text style={[styles.mutedSmall, dark && styles.mutedDark]}>Valore rilevato e riferimento calibrato · ultimi {samples.length} campioni</Text></View><View style={styles.liveLegend}><View style={styles.legendDot}><View style={[styles.miniDot, { backgroundColor: color }]} /><Text style={[styles.legendText, dark && styles.mutedDark]}>Valore</Text></View><View style={styles.legendDot}><View style={[styles.referenceLegendLine, { borderColor: referenceColor }]} /><Text style={[styles.legendText, dark && styles.mutedDark]}>Calibrazione</Text></View></View></View><LineChart data={data} width={width} height={190} segments={6} withDots={false} withShadow={false} withOuterLines={false} yAxisSuffix="°" chartConfig={{ backgroundGradientFrom: dark ? "#162521" : "#fff", backgroundGradientTo: dark ? "#162521" : "#fff", decimalPlaces: 0, color: () => color, labelColor: (opacity = 1) => dark ? `rgba(205,225,219,${opacity})` : `rgba(71,84,103,${opacity})`, propsForBackgroundLines: { stroke: dark ? "#345049" : "#e4eeeb", strokeDasharray: "4 4" } }} style={styles.chart} /></View>;
}

function HistoryAxisChart({ title, samples, period, field, color, width }: { title: string; samples: HistorySample[]; period: HistoryPeriod; field: "pitch_deviation_deg" | "roll_deviation_deg"; color: string; width: number }) {
  const { dark } = useAppTheme();
  const data = {
    labels: samples.map((sample, index) => index === 0 || index === samples.length - 1 ? formatHistoryLabel(sample.timestamp, period) : ""),
    datasets: [{ data: samples.map((sample) => sample[field]), color: () => color, strokeWidth: 2 }],
  };
  return <View style={styles.axisChartBlock}><View style={styles.axisChartTitleRow}><View style={[styles.axisChartMarker, { backgroundColor: color }]} /><Text style={[styles.axisChartTitle, dark && styles.textDark]}>{title}</Text></View><LineChart data={data} width={width} height={190} withDots={false} withOuterLines={false} yAxisSuffix="°" chartConfig={{ backgroundGradientFrom: dark ? "#162521" : "#fff", backgroundGradientTo: dark ? "#162521" : "#fff", decimalPlaces: 0, color: () => color, labelColor: (opacity = 1) => dark ? `rgba(205,225,219,${opacity})` : `rgba(71,84,103,${opacity})`, propsForBackgroundLines: { stroke: dark ? "#345049" : "#e4eeeb", strokeDasharray: "4 4" } }} style={styles.historyChart} /></View>;
}

function Statistic({ label, value, color }: { label: string; value: string; color: string }) {
  const { dark } = useAppTheme();
  return <View style={[styles.statisticBox, dark && styles.surfaceDarkAlt]}><Text style={[styles.statisticValue, { color }]}>{value}</Text><Text style={[styles.statisticLabel, dark && styles.mutedDark]}>{label}</Text></View>;
}

function ProfileScreen({
  session, onSessionUpdate, onBack, onPassword, onSettings, onLogout,
}: {
  session: Session; onSessionUpdate: (session: Session) => void; onBack: () => void; onPassword: () => void; onSettings: () => void; onLogout: () => void;
}) {
  const { dark } = useAppTheme();
  const user = session.user;
  const firstName = user.first_name || user.name.split(" ")[0] || "—";
  const lastName = user.last_name || user.name.split(" ").slice(1).join(" ") || "—";
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  async function chooseAvatar() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert("Accesso alle foto necessario", "Autorizza SmartBack ad accedere alla galleria per scegliere la foto profilo.");
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"], allowsEditing: true, aspect: [1, 1], quality: 0.35, base64: true,
    });
    if (result.canceled) return;
    const asset = result.assets[0];
    if (!asset?.base64) {
      Alert.alert("Foto non disponibile", "Non è stato possibile leggere l'immagine selezionata.");
      return;
    }
    setUploadingAvatar(true);
    try {
      const avatarData = `data:image/jpeg;base64,${asset.base64}`;
      const updatedUser = await api<User>("/api/v1/auth/avatar", { method: "PUT", body: JSON.stringify({ avatar_data: avatarData }) }, session.access_token);
      await onSessionUpdate({ ...session, user: updatedUser });
    } catch (caught) {
      Alert.alert("Foto non aggiornata", caught instanceof Error ? caught.message : "Riprova più tardi.");
    } finally {
      setUploadingAvatar(false);
    }
  }

  function confirmLogout() {
    Alert.alert("Disconnetti account", "Vuoi davvero uscire da SmartBack?", [
      { text: "Annulla", style: "cancel" },
      { text: "Esci", style: "destructive", onPress: onLogout },
    ]);
  }

  return (
    <ScrollView style={dark && styles.screenDark} contentContainerStyle={styles.pageContent}>
      <PageHeading title="Informazioni personali" subtitle="Il tuo profilo SmartBack" onBack={onBack} />
      <View style={[styles.profileHero, dark && styles.surfaceDarkAlt]}>
        <UserAvatar user={user} size={72} />
        <Pressable disabled={uploadingAvatar} onPress={chooseAvatar} style={({ pressed }) => [styles.changePhotoButton, pressed && styles.pressed]}>
          {uploadingAvatar ? <ActivityIndicator color="#087f6a" size="small" /> : <Text style={styles.changePhotoText}>Cambia foto</Text>}
        </Pressable>
        <Text style={[styles.profileName, dark && styles.textDark]}>{firstName} {lastName}</Text>
        <Text style={styles.profileRole}>{user.role === "doctor" ? "Medico" : "Paziente"}</Text>
      </View>
      <View style={[styles.profileCard, dark && styles.surfaceDark]}>
        <ProfileInfo label="NOME" value={firstName} />
        <ProfileInfo label="COGNOME" value={lastName} />
        <ProfileInfo label="EMAIL" value={user.email} last />
      </View>
      <View style={[styles.profileMenu, dark && styles.surfaceDark]}>
        <MenuButton icon="✦" title="Cambia password" subtitle="Aggiorna la password di accesso" onPress={onPassword} />
        <MenuButton icon="⚙" title="Impostazioni" subtitle="Preferenze dell'applicazione" onPress={onSettings} />
        <MenuButton icon="↪" title="Esci dall'account" subtitle="Torna alla schermata di accesso" onPress={confirmLogout} danger last />
      </View>
    </ScrollView>
  );
}

function ChangePasswordScreen({ token, onBack }: { token: string; onBack: () => void }) {
  const { dark } = useAppTheme();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError("");
    if (!currentPassword || !newPassword || !confirmation) {
      setError("Compila tutti i campi.");
      return;
    }
    if (newPassword.length < 8 || !PASSWORD_NUMBER_PATTERN.test(newPassword) || !PASSWORD_SYMBOL_PATTERN.test(newPassword)) {
      setError("La nuova password deve avere almeno 8 caratteri, un numero e un simbolo speciale.");
      return;
    }
    if (newPassword !== confirmation) {
      setError("Le nuove password non coincidono.");
      return;
    }
    if (newPassword === currentPassword) {
      setError("La nuova password deve essere diversa da quella attuale.");
      return;
    }
    setBusy(true);
    try {
      await api("/api/v1/auth/password", { method: "PUT", body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }, token);
      setCurrentPassword(""); setNewPassword(""); setConfirmation("");
      Alert.alert("Password aggiornata", "La password è stata modificata correttamente.", [{ text: "OK", onPress: onBack }]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Impossibile aggiornare la password.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={styles.flexOne} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView style={dark && styles.screenDark} keyboardShouldPersistTaps="handled" contentContainerStyle={styles.pageContent}>
        <PageHeading title="Cambia password" subtitle="Proteggi il tuo account" onBack={onBack} />
        <View style={[styles.formCard, dark && styles.surfaceDark]}>
          <Field label="PASSWORD ATTUALE" value={currentPassword} onChangeText={setCurrentPassword} secureTextEntry autoCapitalize="none" placeholder="Inserisci la password attuale" />
          <Field label="NUOVA PASSWORD" value={newPassword} onChangeText={setNewPassword} secureTextEntry autoCapitalize="none" placeholder="Almeno 8 caratteri" />
          <Field label="CONFERMA NUOVA PASSWORD" value={confirmation} onChangeText={setConfirmation} secureTextEntry autoCapitalize="none" placeholder="Ripeti la nuova password" />
          <Text style={styles.passwordHint}>Deve contenere almeno un numero e un simbolo speciale.</Text>
          {error ? <Text style={styles.formError}>{error}</Text> : null}
          <Pressable disabled={busy} onPress={submit} style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}>
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Salva nuova password</Text>}
          </Pressable>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function SettingsScreen({ nightModeActive, onBack }: { nightModeActive: boolean; onBack: () => void }) {
  const { dark, setDark } = useAppTheme();
  return (
    <ScrollView style={dark && styles.screenDark} contentContainerStyle={styles.pageContent}>
      <PageHeading title="Impostazioni" subtitle="Personalizza la tua esperienza" onBack={onBack} />
      <View style={[styles.settingsCard, dark && styles.surfaceDark]}>
        <View style={styles.settingIcon}><Text style={styles.settingIconText}>☼</Text></View>
        <View style={styles.settingCopy}><Text style={[styles.settingTitle, dark && styles.textDark]}>Tema scuro</Text><Text style={[styles.settingText, dark && styles.mutedDark]}>{nightModeActive ? "Attivo automaticamente durante la modalità notte." : "Riduce la luminosità dell'interfaccia e usa superfici scure."}</Text></View>
        <Switch accessibilityLabel="Attiva tema scuro" disabled={nightModeActive} value={dark} onValueChange={setDark} trackColor={{ false: "#b9ccc7", true: "#4ba996" }} thumbColor={dark ? "#d7fff6" : "#fff"} />
      </View>
      <Text style={[styles.settingsNote, dark && styles.mutedDark]}>La preferenza viene conservata sul dispositivo anche dopo la chiusura dell'app.</Text>
    </ScrollView>
  );
}

function PageHeading({ title, subtitle, onBack }: { title: string; subtitle: string; onBack: () => void }) {
  const { dark } = useAppTheme();
  return <View style={styles.pageHeading}><Pressable accessibilityLabel="Torna indietro" onPress={onBack} style={[styles.backButton, dark && styles.surfaceDark]}><Text style={styles.backButtonText}>‹</Text></Pressable><View style={styles.pageHeadingCopy}><Text style={[styles.pageTitle, dark && styles.textDark]}>{title}</Text><Text style={[styles.pageSubtitle, dark && styles.mutedDark]}>{subtitle}</Text></View></View>;
}

function ProfileInfo({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  const { dark } = useAppTheme();
  return <View style={[styles.profileInfo, dark && styles.borderDark, last && styles.profileInfoLast]}><Text style={[styles.profileInfoLabel, dark && styles.mutedDark]}>{label}</Text><Text style={[styles.profileInfoValue, dark && styles.textDark]}>{value}</Text></View>;
}

function MenuButton({ icon, title, subtitle, onPress, danger = false, last = false }: { icon: string; title: string; subtitle: string; onPress: () => void; danger?: boolean; last?: boolean }) {
  const { dark } = useAppTheme();
  return <Pressable onPress={onPress} style={({ pressed }) => [styles.menuButton, dark && styles.borderDark, last && styles.menuButtonLast, pressed && styles.menuButtonPressed]}><View style={[styles.menuIcon, danger && styles.menuIconDanger]}><Text style={[styles.menuIconText, danger && styles.menuDangerText]}>{icon}</Text></View><View style={styles.menuCopy}><Text style={[styles.menuTitle, dark && styles.textDark, danger && styles.menuDangerText]}>{title}</Text><Text style={[styles.menuSubtitle, dark && styles.mutedDark]}>{subtitle}</Text></View><Text style={[styles.menuChevron, danger && styles.menuDangerText]}>›</Text></Pressable>;
}

function DoctorPatientDirectory({
  patients, loading, onSelect,
}: {
  patients: DoctorPatient[]; loading: boolean; onSelect: (patient: DoctorPatient) => void;
}) {
  const { dark } = useAppTheme();
  return (
    <>
      <View style={styles.directoryHeader}>
        <Text style={[styles.directoryTitle, dark && styles.textDark]}>I miei pazienti</Text>
        <View style={styles.countBadge}><Text style={styles.countText}>{patients.length}</Text></View>
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginVertical: 32 }} color="#087f6a" size="large" />
      ) : patients.length === 0 ? (
        <View style={[styles.emptyPatients, dark && styles.surfaceDark]}><Text style={styles.emptyIcon}>◎</Text><Text style={[styles.waitingTitle, dark && styles.textDark]}>Nessun paziente associato</Text><Text style={[styles.emptyText, dark && styles.mutedDark]}>Le associazioni dei pazienti vengono gestite esternamente all'app.</Text></View>
      ) : patients.map((patient) => (
        <Pressable key={patient.id} onPress={() => onSelect(patient)} style={({ pressed }) => [styles.patientCard, dark && styles.surfaceDark, pressed && styles.patientCardPressed]}>
          <UserAvatar user={patient} size={48} />
          <View style={{ flex: 1 }}><Text style={[styles.patientCardName, dark && styles.textDark]}>{patient.name}</Text><Text style={[styles.patientEmail, dark && styles.mutedDark]}>{patient.email}</Text><Text style={styles.patientCode}>{patient.patient_code}</Text></View>
          <View style={styles.patientCardRight}>{patient.has_live_data && <View style={styles.onlineBadge}><View style={styles.miniDot} /><Text style={styles.onlineText}>Live</Text></View>}<Text style={styles.chevron}>›</Text></View>
        </Pressable>
      ))}
    </>
  );
}

function Logo({ large = false }: { large?: boolean }) {
  return <SmartBackLogo large={large} />;
}

function UserAvatar({ user, size, accentColor = "#087f6a" }: { user: User | null; size: number; accentColor?: string }) {
  const initial = user?.first_name?.charAt(0) || user?.name?.charAt(0) || "?";
  const avatarStyle = { width: size, height: size, borderRadius: size / 2, backgroundColor: user?.avatar_data ? "#dceae6" : accentColor };
  return (
    <View style={[styles.userAvatar, avatarStyle]}>
      {user?.avatar_data ? <Image source={{ uri: user.avatar_data }} style={avatarStyle} resizeMode="cover" /> : <Text style={[styles.userAvatarText, { fontSize: Math.max(14, size * 0.4) }]}>{initial.toUpperCase()}</Text>}
    </View>
  );
}

function Field(props: React.ComponentProps<typeof TextInput> & { label: string }) {
  const { label, ...inputProps } = props;
  const { dark } = useAppTheme();
  const [focused, setFocused] = useState(false);
  return <View style={styles.field}><Text style={[styles.inputLabel, dark && styles.mutedDark]}>{label}</Text><TextInput {...inputProps} onFocus={(event) => { setFocused(true); inputProps.onFocus?.(event); }} onBlur={(event) => { setFocused(false); inputProps.onBlur?.(event); }} placeholderTextColor={dark ? "#7f9a93" : "#98aaa5"} style={[styles.input, dark && styles.inputDark, focused && styles.inputFocused, inputProps.style]} /></View>;
}

function RoleButton({ selected, label, onPress }: { selected: boolean; label: string; onPress: () => void }) {
  const { dark } = useAppTheme();
  return <Pressable onPress={onPress} style={[styles.roleButton, dark && styles.surfaceDarkAlt, selected && styles.roleButtonSelected]}><Text style={[styles.roleText, dark && styles.mutedDark, selected && styles.roleTextSelected]}>{label}</Text></Pressable>;
}

function Metric({ label, value }: { label: string; value: string }) {
  const { dark } = useAppTheme();
  return <View style={[styles.metricCard, dark && styles.surfaceDark]}><Text style={[styles.metricLabel, dark && styles.mutedDark]}>{label}</Text><Text style={[styles.metricValue, dark && styles.textDark]}>{value}</Text></View>;
}

function PatientDeviceSummary({ deviceId, battery }: { deviceId: string | null; battery: number | null }) {
  const { dark } = useAppTheme();
  return <View style={[styles.deviceSummary, dark && styles.surfaceDark]}><View style={styles.deviceSummaryItem}><Text style={styles.deviceSummaryIcon}>▣</Text><View style={{ flex: 1 }}><Text style={[styles.metricLabel, dark && styles.mutedDark]}>Tipo dispositivo</Text><Text numberOfLines={1} style={[styles.deviceSummaryValue, dark && styles.textDark]}>{deviceId ? `Smart t-shirt · ${deviceId}` : "Non rilevato"}</Text></View></View><View style={styles.deviceSummaryDivider} /><View style={styles.deviceSummaryItem}><Text style={styles.deviceSummaryIcon}>ϟ</Text><View style={{ flex: 1 }}><Text style={[styles.metricLabel, dark && styles.mutedDark]}>Batteria</Text><Text style={[styles.deviceSummaryValue, dark && styles.textDark]}>{battery != null ? `${battery}%` : "—"}</Text></View></View></View>;
}

function formatHistoryLabel(timestamp: string, period: HistoryPeriod) {
  const date = new Date(timestamp);
  return period >= 1440
    ? date.toLocaleDateString("it-IT", { day: "2-digit", month: "2-digit" })
    : date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
}

function formatNightSessionLabel(session: NightSession) {
  const date = new Date(session.started_at);
  return `${date.toLocaleDateString("it-IT", { day: "2-digit", month: "long", year: "numeric" })} · ${date.toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" })}`;
}

function formatSigned(value: number) { return `${value > 0 ? "+" : ""}${value.toFixed(1)}°`; }
function formatDuration(seconds: number) {
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainingSeconds = total % 60;
  if (hours) return `${hours}h ${minutes}m`;
  if (minutes) return `${minutes}m ${remainingSeconds}s`;
  return `${remainingSeconds}s`;
}

function isValidFiscalCode(value: string) {
  const code = value.toUpperCase().replace(/\s/g, "");
  if (!FISCAL_CODE_PATTERN.test(code)) return false;
  const oddSequence = [1, 0, 5, 7, 9, 13, 15, 17, 19, 21, 2, 4, 18, 20, 11, 3, 6, 8, 12, 14, 16, 10, 22, 25, 24, 23];
  const oddValue = (character: string) => oddSequence[Number.isNaN(Number(character)) ? character.charCodeAt(0) - 65 : Number(character)];
  const evenValue = (character: string) => Number.isNaN(Number(character)) ? character.charCodeAt(0) - 65 : Number(character);
  const total = code.slice(0, 15).split("").reduce((sum, character, index) => sum + (index % 2 === 0 ? oddValue(character) : evenValue(character)), 0);
  return code.charCodeAt(15) === 65 + total % 26;
}

const styles = StyleSheet.create({
  flexOne: { flex: 1 },
  centerScreen: { flex: 1, backgroundColor: "#edf7f4", alignItems: "center", justifyContent: "center" },
  authSafe: { flex: 1, backgroundColor: "#e5f5f1" }, authKeyboard: { flex: 1 },
  authContent: { flexGrow: 1, padding: 24, paddingTop: 48, paddingBottom: 34, alignItems: "center" },
  logoRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  logoImage: { width: 128, height: 52 }, logoImageLarge: { width: 260, height: 190 },
  logoMark: { width: 35, height: 35, borderRadius: 11, backgroundColor: "#087f6a", alignItems: "center", justifyContent: "center", transform: [{ rotate: "-8deg" }] },
  logoMarkLarge: { width: 48, height: 48, borderRadius: 15 }, logoSpine: { width: 9, height: 22, borderRadius: 6, backgroundColor: "#b9ede2" },
  logoName: { color: "#123c34", fontSize: 21, lineHeight: 22, fontWeight: "900", letterSpacing: -0.7 }, logoNameLarge: { fontSize: 29, lineHeight: 30 },
  logoSub: { color: "#429385", fontSize: 7, fontWeight: "800", letterSpacing: 1.25 }, authClaim: { marginTop: 4, color: "#42655f", fontSize: 14 },
  authCard: { width: "100%", maxWidth: 460, marginTop: 30, backgroundColor: "#fff", borderRadius: 26, padding: 22, shadowColor: "#0a4c40", shadowOpacity: 0.08, shadowRadius: 20, shadowOffset: { width: 0, height: 8 }, elevation: 3 },
  authTitle: { color: "#153d35", fontSize: 25, fontWeight: "900", letterSpacing: -0.5 }, authSubtitle: { color: "#6b817c", marginTop: 5, marginBottom: 22, lineHeight: 19 },
  field: { marginTop: 14 }, inputLabel: { color: "#54756e", fontSize: 10, fontWeight: "800", letterSpacing: 0.8, marginBottom: 7 },
  input: { minHeight: 50, borderWidth: 1, borderColor: "#cfe2dd", borderRadius: 14, paddingHorizontal: 15, color: "#153d35", fontSize: 15, backgroundColor: "#fbfefd" },
  inputFocused: { borderColor: "#20a38c", shadowColor: "#087f6a", shadowOpacity: 0.24, shadowRadius: 9, shadowOffset: { width: 0, height: 3 }, elevation: 5 },
  roleRow: { flexDirection: "row", gap: 10, marginBottom: 3 }, roleButton: { flex: 1, minHeight: 48, borderWidth: 1, borderColor: "#cfe2dd", borderRadius: 14, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  roleButtonSelected: { borderColor: "#20a38c", backgroundColor: "#e7f8f4" }, radio: { width: 17, height: 17, borderRadius: 9, borderWidth: 1.5, borderColor: "#91aaa4", alignItems: "center", justifyContent: "center" },
  radioSelected: { borderColor: "#087f6a" }, radioInner: { width: 9, height: 9, borderRadius: 5, backgroundColor: "#087f6a" }, roleText: { color: "#617b75", fontWeight: "700" }, roleTextSelected: { color: "#087f6a" },
  formError: { color: "#b42318", fontSize: 12, marginTop: 13, lineHeight: 17 }, primaryButton: { minHeight: 52, borderRadius: 15, backgroundColor: "#087f6a", alignItems: "center", justifyContent: "center", marginTop: 18, paddingHorizontal: 18 },
  primaryText: { color: "#fff", fontWeight: "900", fontSize: 15 }, pressed: { opacity: 0.82 }, switchText: { color: "#54756e", textAlign: "center", fontWeight: "600", marginTop: 20, fontSize: 13 }, switchLink: { color: "#087f6a", fontWeight: "900", textDecorationLine: "underline" }, demoNote: { color: "#71918a", marginTop: 24, fontSize: 10, textAlign: "center" },
  dashboardSafe: { flex: 1, backgroundColor: "#f1f7f5" }, fixedHeader: { minHeight: 68, backgroundColor: "#fff", borderBottomWidth: 1, borderBottomColor: "#dceae6", paddingHorizontal: 20, flexDirection: "row", alignItems: "center", justifyContent: "space-between", zIndex: 10 },
  headerBrandSmart: { color: "#123f70", fontSize: 23, lineHeight: 27, fontWeight: "900", letterSpacing: -0.8 }, headerBrandBack: { color: "#123f70", fontWeight: "400", letterSpacing: -0.5 },
  headerRight: { flexDirection: "row", alignItems: "center", gap: 10 }, liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#12b76a" },
  avatar: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#c8eee6", alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "transparent" }, avatarSelected: { borderColor: "#087f6a", backgroundColor: "#e3f7f2" }, avatarText: { color: "#087f6a", fontWeight: "900" }, dashboardContent: { padding: 18, paddingBottom: 38, gap: 14 },
  welcome: { color: "#153d35", fontSize: 24, fontWeight: "900", letterSpacing: -0.5 }, roleCaption: { color: "#6b817c", marginTop: 3, fontSize: 12 }, waitingCard: { minHeight: 260, borderRadius: 24, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", gap: 10, padding: 24 }, waitingTitle: { color: "#153d35", fontSize: 18, fontWeight: "800" }, muted: { color: "#6b817c", fontSize: 12 },
  patientStrip: { backgroundColor: "#dff4ef", borderRadius: 16, padding: 14, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, overline: { color: "#438579", fontSize: 8, fontWeight: "900", letterSpacing: 1 }, patientName: { color: "#153d35", fontWeight: "800", marginTop: 3 }, patientCode: { color: "#5f817a", fontSize: 9 },
  postureCard: { padding: 18, borderRadius: 22, gap: 20 }, postureTop: { flexDirection: "row", gap: 13, alignItems: "flex-start" }, postureLabel: { fontSize: 19, fontWeight: "900" }, postureDetail: { color: "#526d67", fontSize: 12, lineHeight: 18, marginTop: 3 },
  deviationRow: { borderTopWidth: 1, borderTopColor: "rgba(30,70,60,.12)", paddingTop: 14, flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }, deviationCaption: { color: "#66817b", fontSize: 8, fontWeight: "900", letterSpacing: 0.7, flex: 1 }, deviationValue: { fontSize: 33, lineHeight: 37, fontWeight: "900", letterSpacing: -1 },
  metricsRow: { flexDirection: "row", gap: 9 }, metricCard: { flex: 1, backgroundColor: "#fff", padding: 13, borderRadius: 15 }, metricLabel: { color: "#78908a", fontSize: 10, fontWeight: "700" }, metricValue: { color: "#153d35", fontSize: 18, fontWeight: "900", marginTop: 4 },
  calibrationHeading: { color: "#153d35", fontSize: 14, fontWeight: "900", marginBottom: 8 }, calibrationRow: { flexDirection: "row", gap: 9 }, calibrationCard: { flex: 1, minHeight: 74, backgroundColor: "#fff", borderRadius: 15, padding: 13, justifyContent: "center" }, calibrationLabel: { color: "#78908a", fontSize: 9, fontWeight: "800" }, calibrationValue: { fontSize: 21, fontWeight: "900", marginTop: 4 }, pitchCalibrationValue: { color: "#1e40af" }, rollCalibrationValue: { color: "#d94f9b" },
  whiteCard: { backgroundColor: "#fff", borderRadius: 21, paddingTop: 17, overflow: "hidden" }, sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", paddingHorizontal: 17 }, sectionTitle: { color: "#153d35", fontSize: 16, fontWeight: "900" }, mutedSmall: { color: "#78908a", fontSize: 10, marginTop: 3 }, legendDot: { flexDirection: "row", alignItems: "center", gap: 5 }, miniDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#087f6a" }, legendText: { color: "#78908a", fontSize: 9 }, chart: { marginLeft: -13, marginTop: 8 },
  liveChartHeading: { flex: 1, paddingRight: 8 }, liveLegend: { gap: 5, alignItems: "flex-start" }, referenceLegendLine: { width: 13, height: 3, borderTopWidth: 2, borderStyle: "dashed" },
  deviceSummary: { backgroundColor: "#fff", borderRadius: 16, padding: 12, flexDirection: "row", alignItems: "center", borderWidth: 1, borderColor: "#dceae6" }, deviceSummaryItem: { flex: 1, flexDirection: "row", alignItems: "center", gap: 9 }, deviceSummaryIcon: { color: "#20a38c", fontSize: 19 }, deviceSummaryValue: { color: "#153d35", fontWeight: "800", fontSize: 11, marginTop: 3 }, deviceSummaryDivider: { width: 1, height: 34, backgroundColor: "#dceae6", marginHorizontal: 11 },
  notificationCard: { backgroundColor: "#dff5f0", borderRadius: 17, padding: 14, flexDirection: "row", alignItems: "center", gap: 12 }, bellCircle: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#b9e9df", alignItems: "center", justifyContent: "center" }, bell: { color: "#087f6a", fontSize: 17 }, notificationTitle: { color: "#153d35", fontWeight: "900", fontSize: 13 }, notificationText: { color: "#56766f", fontSize: 10, lineHeight: 15, marginTop: 2 }, message: { color: "#42655f", textAlign: "center", fontSize: 11 }, disclaimer: { color: "#8ba09b", textAlign: "center", fontSize: 9, marginTop: 4 },
  nightCard: { borderRadius: 24, padding: 18, backgroundColor: "#16233a", borderWidth: 1, borderColor: "#2d4163", gap: 15, shadowColor: "#07101f", shadowOpacity: 0.18, shadowRadius: 14, shadowOffset: { width: 0, height: 7 }, elevation: 4 }, nightCardActive: { borderColor: "#3d806f" }, nightCardDark: { backgroundColor: "#111d2d", borderColor: "#294b46" }, nightHeader: { flexDirection: "row", alignItems: "center", gap: 11 }, nightMoon: { width: 43, height: 43, borderRadius: 22, backgroundColor: "#243b60", alignItems: "center", justifyContent: "center" }, nightMoonText: { color: "#c8dcff", fontSize: 28, lineHeight: 31 }, nightTitle: { color: "#f1f6ff", fontSize: 18, fontWeight: "900" }, nightSubtitle: { color: "#9eb0cc", fontSize: 10, marginTop: 3 }, nightLiveBadge: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: "#173c34", borderRadius: 12, paddingHorizontal: 9, paddingVertical: 6 }, nightLiveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#3ec6ae" }, nightLiveText: { color: "#75e0cc", fontSize: 8, fontWeight: "900", letterSpacing: 0.8 }, nightDescription: { color: "#b2bfd2", fontSize: 11, lineHeight: 17 }, nightPositionBox: { backgroundColor: "#101a2b", borderRadius: 18, padding: 17, alignItems: "center", borderWidth: 1, borderColor: "#263a5a" }, nightOverline: { color: "#7e91af", fontSize: 8, fontWeight: "900", letterSpacing: 1 }, nightPosition: { fontSize: 23, fontWeight: "900", marginTop: 7, textAlign: "center" }, nightWaitingText: { color: "#9eb0cc", fontSize: 9, marginTop: 5 }, nightStatsGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 }, nightStat: { width: "48%", flexGrow: 1, minHeight: 66, backgroundColor: "#101a2b", borderRadius: 14, padding: 11, borderWidth: 1, borderColor: "#263750" }, nightStatDot: { width: 7, height: 7, borderRadius: 4, position: "absolute", top: 11, right: 11 }, nightStatValue: { color: "#f1f6ff", fontSize: 16, fontWeight: "900" }, nightStatLabel: { color: "#8fa1bd", fontSize: 9, marginTop: 4 }, nightPieCard: { backgroundColor: "#101a2b", borderRadius: 18, paddingTop: 14, paddingHorizontal: 10, borderWidth: 1, borderColor: "#263750", overflow: "hidden" }, nightPieChart: { alignSelf: "center" }, nightPieEmpty: { color: "#9eb0cc", fontSize: 10, lineHeight: 16, textAlign: "center", paddingVertical: 35, paddingHorizontal: 12 }, nightMeta: { flexDirection: "row", justifyContent: "space-between", gap: 10 }, nightMetaText: { color: "#9eb0cc", fontSize: 9, fontWeight: "700" }, nightError: { color: "#ffb4a8", fontSize: 10, lineHeight: 15 }, nightButton: { minHeight: 50, borderRadius: 15, backgroundColor: "#087f6a", alignItems: "center", justifyContent: "center", paddingHorizontal: 14 }, nightStopButton: { backgroundColor: "#a33d3d" }, nightButtonText: { color: "#fff", fontSize: 12, fontWeight: "900", letterSpacing: 0.6 },
  monitoringSectionHeader: { minHeight: 72, borderRadius: 19, padding: 14, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1 }, monitoringSectionDay: { backgroundColor: "#e6f7f3", borderColor: "#b4e3d9" }, monitoringSectionNight: { backgroundColor: "#e9eef8", borderColor: "#c8d5ec" }, monitoringSectionHeaderDark: { backgroundColor: "#172621", borderColor: "#355149" }, monitoringSectionIcon: { width: 43, height: 43, borderRadius: 22, alignItems: "center", justifyContent: "center" }, monitoringSectionIconDay: { backgroundColor: "#bdebe1" }, monitoringSectionIconNight: { backgroundColor: "#243b60" }, monitoringSectionIconText: { color: "#087f6a", fontSize: 22, fontWeight: "900" }, monitoringSectionTitle: { color: "#153d35", fontSize: 18, fontWeight: "900" }, monitoringSectionSubtitle: { color: "#658079", fontSize: 10, lineHeight: 15, marginTop: 2 }, doctorNightSection: { gap: 14, marginTop: 8, paddingTop: 16, borderTopWidth: 2, borderTopColor: "#d8e1ef" }, nightHistoryCard: { backgroundColor: "#fff", borderRadius: 21, paddingTop: 17, paddingBottom: 16, overflow: "hidden" }, nightPeriodButton: { borderColor: "#ccd7eb" }, nightPeriodButtonSelected: { backgroundColor: "#315f9a", borderColor: "#315f9a" }, nightHistoryEmpty: { color: "#78908a", fontSize: 11, textAlign: "center", paddingHorizontal: 18, paddingVertical: 20 }, nightChartCaption: { color: "#718294", fontSize: 9, textAlign: "center", paddingHorizontal: 17, marginTop: 4 }, sessionSelectorWrap: { paddingHorizontal: 14, marginTop: 15 }, sessionSelector: { minHeight: 48, borderRadius: 13, borderWidth: 1, borderColor: "#ccd7eb", backgroundColor: "#f8fafc", paddingHorizontal: 13, flexDirection: "row", alignItems: "center", gap: 8 }, sessionSelectorText: { flex: 1, color: "#28445d", fontSize: 11, fontWeight: "800" }, sessionSelectorChevron: { color: "#315f9a", fontSize: 18, fontWeight: "900" }, sessionDropdown: { marginTop: 7, borderRadius: 14, borderWidth: 1, borderColor: "#ccd7eb", backgroundColor: "#fff", padding: 9, shadowColor: "#17324d", shadowOpacity: 0.1, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 4 }, sessionSearchInput: { minHeight: 42, borderWidth: 1, borderColor: "#d6dfed", borderRadius: 11, paddingHorizontal: 12, color: "#17324d", fontSize: 11, backgroundColor: "#f8fafc" }, sessionOptionsScroll: { maxHeight: 230, marginTop: 6 }, sessionOption: { minHeight: 54, borderRadius: 10, paddingHorizontal: 11, paddingVertical: 9, justifyContent: "center", borderBottomWidth: 1, borderBottomColor: "#e7ecf4" }, sessionOptionSelected: { backgroundColor: "#e7eef9" }, sessionOptionTitle: { color: "#17324d", fontSize: 11, fontWeight: "900" }, sessionOptionMeta: { color: "#718294", fontSize: 9, marginTop: 3 }, sessionSearchEmpty: { color: "#78908a", fontSize: 10, textAlign: "center", padding: 20 }, nightHistogram: { height: 230, marginHorizontal: 14, marginTop: 17, position: "relative", borderBottomWidth: 1, borderBottomColor: "#d9e2ef" }, histogramGuideTop: { position: "absolute", left: 0, right: 0, top: 21, borderBottomWidth: 1, borderBottomColor: "#e3e9f2" }, histogramGuideMiddle: { position: "absolute", left: 0, right: 0, top: 96, borderBottomWidth: 1, borderBottomColor: "#e3e9f2" }, histogramGuideText: { position: "absolute", top: -12, left: 0, color: "#91a0b2", fontSize: 7 }, histogramBars: { position: "absolute", left: 22, right: 0, top: 0, bottom: 0, flexDirection: "row", alignItems: "flex-end", justifyContent: "space-around" }, histogramColumn: { width: "23%", height: 220, alignItems: "center", justifyContent: "flex-end" }, histogramValue: { color: "#17324d", fontSize: 11, fontWeight: "900", marginBottom: 5 }, histogramTrack: { height: 150, width: 36, justifyContent: "flex-end", backgroundColor: "#edf1f6", borderTopLeftRadius: 7, borderTopRightRadius: 7, overflow: "hidden" }, histogramBar: { width: "100%", borderTopLeftRadius: 7, borderTopRightRadius: 7 }, histogramLabel: { height: 35, color: "#718294", fontSize: 8, fontWeight: "800", lineHeight: 11, textAlign: "center", marginTop: 5 },
  directoryHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 5 }, directoryTitle: { color: "#153d35", fontSize: 19, fontWeight: "900" }, countBadge: { minWidth: 25, height: 25, paddingHorizontal: 7, borderRadius: 13, backgroundColor: "#cceee7", alignItems: "center", justifyContent: "center" }, countText: { color: "#087f6a", fontSize: 11, fontWeight: "900" },
  emptyPatients: { minHeight: 210, borderRadius: 21, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", padding: 28 }, emptyIcon: { color: "#64b9aa", fontSize: 38, marginBottom: 8 }, emptyText: { color: "#78908a", fontSize: 12, textAlign: "center", lineHeight: 18, marginTop: 5 },
  patientCard: { minHeight: 84, borderRadius: 18, backgroundColor: "#fff", padding: 14, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1, borderColor: "#e0ece9" }, patientCardPressed: { backgroundColor: "#edf8f5", borderColor: "#9cd8cc" }, patientCardName: { color: "#153d35", fontSize: 15, fontWeight: "900" }, patientEmail: { color: "#67817b", fontSize: 11, marginTop: 2 }, patientCardRight: { alignItems: "flex-end", gap: 8 }, onlineBadge: { flexDirection: "row", alignItems: "center", gap: 4, borderRadius: 10, backgroundColor: "#e4f7ee", paddingHorizontal: 7, paddingVertical: 4 }, onlineText: { color: "#087f6a", fontSize: 8, fontWeight: "900" }, chevron: { color: "#5e8f85", fontSize: 25, lineHeight: 25 }, backArrow: { color: "#087f6a", fontSize: 28, lineHeight: 30, marginRight: 8 },
  pageContent: { flexGrow: 1, padding: 18, paddingBottom: 42, gap: 16 }, pageHeading: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 2 }, backButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#fff", borderWidth: 1, borderColor: "#dceae6", alignItems: "center", justifyContent: "center" }, backButtonText: { color: "#087f6a", fontSize: 30, lineHeight: 31, marginTop: -2 }, pageHeadingCopy: { flex: 1 }, pageTitle: { color: "#153d35", fontSize: 23, fontWeight: "900", letterSpacing: -0.5 }, pageSubtitle: { color: "#6b817c", fontSize: 12, marginTop: 2 },
  profileHero: { alignItems: "center", backgroundColor: "#dff4ef", borderRadius: 24, paddingVertical: 24, paddingHorizontal: 18 }, userAvatar: { alignItems: "center", justifyContent: "center", overflow: "hidden" }, userAvatarText: { color: "#fff", fontWeight: "900" }, changePhotoButton: { minHeight: 34, minWidth: 116, borderRadius: 17, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", paddingHorizontal: 14, marginTop: 10, borderWidth: 1, borderColor: "#a8d9cf" }, changePhotoText: { color: "#087f6a", fontSize: 11, fontWeight: "900" }, profileName: { color: "#153d35", fontSize: 21, fontWeight: "900", marginTop: 12 }, profileRole: { color: "#087f6a", fontSize: 11, fontWeight: "800", marginTop: 4, textTransform: "uppercase", letterSpacing: 0.8 },
  profileCard: { backgroundColor: "#fff", borderRadius: 21, paddingHorizontal: 17 }, profileInfo: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: "#e6efed" }, profileInfoLast: { borderBottomWidth: 0 }, profileInfoLabel: { color: "#78908a", fontSize: 9, fontWeight: "900", letterSpacing: 0.8 }, profileInfoValue: { color: "#153d35", fontSize: 15, fontWeight: "700", marginTop: 4 },
  profileMenu: { backgroundColor: "#fff", borderRadius: 21, paddingHorizontal: 15 }, menuButton: { minHeight: 72, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: "#e6efed" }, menuButtonLast: { borderBottomWidth: 0 }, menuButtonPressed: { opacity: 0.65 }, menuIcon: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#dff5f0", alignItems: "center", justifyContent: "center" }, menuIconDanger: { backgroundColor: "#fee9e7" }, menuIconText: { color: "#087f6a", fontSize: 17, fontWeight: "900" }, menuDangerText: { color: "#b42318" }, menuCopy: { flex: 1 }, menuTitle: { color: "#153d35", fontSize: 14, fontWeight: "900" }, menuSubtitle: { color: "#78908a", fontSize: 10, marginTop: 3 }, menuChevron: { color: "#6f9189", fontSize: 26 },
  formCard: { backgroundColor: "#fff", borderRadius: 23, padding: 19 }, passwordHint: { color: "#78908a", fontSize: 10, lineHeight: 15, marginTop: 11 }, settingsCard: { backgroundColor: "#fff", borderRadius: 21, padding: 17, flexDirection: "row", alignItems: "center", gap: 12 }, settingIcon: { width: 45, height: 45, borderRadius: 23, backgroundColor: "#dff5f0", alignItems: "center", justifyContent: "center" }, settingIconText: { color: "#087f6a", fontSize: 22 }, settingCopy: { flex: 1 }, settingTitle: { color: "#153d35", fontSize: 15, fontWeight: "900" }, settingText: { color: "#78908a", fontSize: 10, lineHeight: 15, marginTop: 3 }, soonBadge: { backgroundColor: "#edf4f2", borderRadius: 10, paddingHorizontal: 7, paddingVertical: 5 }, soonText: { color: "#608078", fontSize: 7, fontWeight: "900", letterSpacing: 0.4 }, settingsNote: { color: "#78908a", fontSize: 11, lineHeight: 17, textAlign: "center", paddingHorizontal: 18 },
  historyCard: { backgroundColor: "#fff", borderRadius: 21, paddingTop: 17, overflow: "hidden" }, historyHeading: { minHeight: 38, paddingHorizontal: 17, flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" }, periodRow: { flexDirection: "row", gap: 6, paddingHorizontal: 14, marginTop: 14 }, periodButton: { flex: 1, minHeight: 34, borderRadius: 11, borderWidth: 1, borderColor: "#d6e5e1", alignItems: "center", justifyContent: "center", backgroundColor: "#fbfefd" }, periodButtonSelected: { backgroundColor: "#087f6a", borderColor: "#087f6a" }, periodText: { color: "#5d7771", fontSize: 9, fontWeight: "800" }, periodTextSelected: { color: "#fff" }, historyLegend: { flexDirection: "row", justifyContent: "flex-end", gap: 13, paddingHorizontal: 17, marginTop: 12 }, legendItem: { flexDirection: "row", alignItems: "center", gap: 5 }, historyLegendDot: { width: 8, height: 8, borderRadius: 4 }, correctDot: { backgroundColor: "#25a995" }, incorrectDot: { backgroundColor: "#d92d20" }, historyChart: { marginLeft: -13, marginTop: 2 }, axisChartBlock: { borderTopWidth: 1, borderTopColor: "#e4eeeb", marginTop: 13, paddingTop: 13 }, axisChartTitleRow: { flexDirection: "row", alignItems: "center", gap: 7, paddingHorizontal: 17 }, axisChartMarker: { width: 9, height: 9, borderRadius: 5 }, axisChartTitle: { color: "#29433d", fontSize: 12, fontWeight: "900" }, noHistoryText: { color: "#78908a", fontSize: 10, textAlign: "center", paddingHorizontal: 16, paddingBottom: 15, marginTop: -7 },
  patientHistoryPercentages: { flexDirection: "row", gap: 9, padding: 14, marginTop: 4 }, statisticBox: { width: "48%", flexGrow: 1, minHeight: 82, borderRadius: 15, backgroundColor: "#f3f8f7", padding: 13, justifyContent: "center" }, statisticValue: { fontSize: 22, fontWeight: "900" }, statisticLabel: { color: "#6b817c", fontSize: 10, fontWeight: "700", marginTop: 4 },
  screenDark: { backgroundColor: "#0d1714" }, headerDark: { backgroundColor: "#13211d", borderBottomColor: "#29433d" }, surfaceDark: { backgroundColor: "#162521", borderColor: "#29433d" }, surfaceDarkAlt: { backgroundColor: "#20332e", borderColor: "#355149" }, textDark: { color: "#e7f4f0" }, mutedDark: { color: "#9eb9b1" }, borderDark: { borderBottomColor: "#29433d" }, inputDark: { backgroundColor: "#20332e", borderColor: "#355149", color: "#e7f4f0" },
});

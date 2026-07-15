import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import * as SecureStore from "expo-secure-store";
import { StatusBar } from "expo-status-bar";
import { LineChart } from "react-native-chart-kit";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { SmartBackLogo } from "./SmartBackLogo";

type Role = "patient" | "doctor";
type User = { id: string; name: string; first_name?: string; last_name?: string; email: string; role: Role; patient_code?: string | null; professional_verified?: boolean };
type Session = { access_token: string; user: User };
type DoctorPatient = User & { associated_at?: string; has_live_data: boolean };
type PostureStatus = "neutral" | "deviated" | "prolonged_deviation" | "marked_deviation";
type PostureSample = {
  timestamp: number; device_id: string; patient_id: string;
  pitch_deg: number; roll_deg: number; reference_pitch_deg: number;
  deviation_deg: number; deviation_duration_seconds: number;
  posture_status: PostureStatus; alert: string | null; threshold_profile: string;
};
type DeviceStatus = { device_id: string; state_of_charge?: number; charging?: boolean };
type ConnectionState = "connecting" | "connected" | "disconnected";
type AppScreen = "dashboard" | "profile" | "password" | "settings";

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_URL = process.env.EXPO_PUBLIC_WS_URL ?? "ws://localhost:8000/ws/wearable";
const SESSION_KEY = "smartback.session";
const MAX_SAMPLES = 30;
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
  return <SafeAreaProvider><AppContent /></SafeAreaProvider>;
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
  return <Dashboard session={session} onLogout={logout} />;
}

function LoadingScreen() {
  return (
    <SafeAreaView style={styles.centerScreen}>
      <StatusBar style="dark" />
      <Logo />
      <ActivityIndicator style={{ marginTop: 24 }} color="#087f6a" size="large" />
    </SafeAreaView>
  );
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
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
    <SafeAreaView style={styles.authSafe}>
      <StatusBar style="dark" />
      <KeyboardAvoidingView style={styles.authKeyboard} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.authContent} keyboardShouldPersistTaps="handled">
          <Logo large />
          <Text style={styles.authClaim}>La postura guidata dai dati</Text>
          <View style={styles.authCard}>
            <Text style={styles.authTitle}>{mode === "login" ? "Bentornato" : "Crea il tuo profilo"}</Text>
            <Text style={styles.authSubtitle}>{mode === "login" ? "Accedi al monitoraggio posturale" : "Registrati con i tuoi dati"}</Text>

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

function Dashboard({ session, onLogout }: { session: Session; onLogout: () => void }) {
  const { width } = useWindowDimensions();
  const [screen, setScreen] = useState<AppScreen>("dashboard");
  const [samples, setSamples] = useState<PostureSample[]>([]);
  const [device, setDevice] = useState<DeviceStatus | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [message, setMessage] = useState("");
  const [calibrating, setCalibrating] = useState(false);
  const [doctorPatients, setDoctorPatients] = useState<DoctorPatient[]>([]);
  const [selectedPatient, setSelectedPatient] = useState<DoctorPatient | null>(null);
  const [associationEmail, setAssociationEmail] = useState("");
  const [patientsLoading, setPatientsLoading] = useState(session.user.role === "doctor");
  const [associating, setAssociating] = useState(false);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const visibleSamples = session.user.role === "doctor"
    ? samples.filter((sample) => sample.patient_id === selectedPatient?.patient_code)
    : samples;
  const latest = visibleSamples[visibleSamples.length - 1];
  const posture = latest ? postureStyles[latest.posture_status] : null;

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

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    function connect() {
      if (!active) return;
      setConnection("connecting");
      socket = new WebSocket(WS_URL);
      socket.onopen = () => { if (active) { setConnection("connected"); setMessage(""); } };
      socket.onmessage = (event) => {
        try {
          const sample = JSON.parse(event.data) as PostureSample;
          if (typeof sample.deviation_deg === "number") setSamples((current) => [...current.slice(-(MAX_SAMPLES - 1)), sample]);
        } catch { setMessage("Dato ricevuto non valido."); }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (!active) return;
        setConnection("disconnected");
        setMessage("Connessione in pausa. Riprovo automaticamente…");
        reconnectTimer.current = setTimeout(connect, 3000);
      };
    }
    connect();
    return () => { active = false; if (reconnectTimer.current) clearTimeout(reconnectTimer.current); socket?.close(); };
  }, []);

  const chartData = useMemo(() => ({
    labels: visibleSamples.map((_, index) => index === 0 || index === visibleSamples.length - 1 ? `${index + 1}` : ""),
    datasets: [{ data: visibleSamples.length ? visibleSamples.map((sample) => sample.deviation_deg) : [0], color: () => "#087f6a", strokeWidth: 3 }],
  }), [visibleSamples]);

  async function associatePatient() {
    const email = associationEmail.trim().toLowerCase();
    if (!EMAIL_PATTERN.test(email)) {
      Alert.alert("Email non valida", "Inserisci l’email usata dal paziente per registrarsi.");
      return;
    }
    setAssociating(true);
    try {
      await api("/api/v1/doctor/patients", { method: "POST", body: JSON.stringify({ email }) }, session.access_token);
      setAssociationEmail("");
      await loadDoctorPatients();
      Alert.alert("Associazione completata", "Il paziente è stato aggiunto alla tua lista.");
    } catch (caught) {
      Alert.alert("Associazione non riuscita", caught instanceof Error ? caught.message : "Riprova più tardi");
    } finally {
      setAssociating(false);
    }
  }

  async function calibrate() {
    if (!latest || calibrating) return;
    setCalibrating(true); setMessage("");
    try {
      await api(`/api/v1/devices/${latest.device_id}/calibration`, { method: "POST" });
      setMessage("Nuova postura di riferimento acquisita.");
    } catch { setMessage("Calibrazione non riuscita."); }
    finally { setCalibrating(false); }
  }

  const connectionLabel = connection === "connected" ? "Live" : connection === "connecting" ? "Connessione…" : "Offline";
  const roleLabel = session.user.role === "doctor" ? "Medico" : "Paziente";

  return (
    <SafeAreaView edges={["top", "left", "right"]} style={styles.dashboardSafe}>
      <StatusBar style="dark" />
      <View style={styles.fixedHeader}>
        <Pressable onPress={() => setScreen("dashboard")}><Text style={styles.headerBrand}>SmartBack</Text></Pressable>
        <View style={styles.headerRight}>
          <View style={styles.liveBadge}><View style={[styles.liveDot, connection !== "connected" && styles.liveDotOffline]} /><Text style={styles.liveText}>{connectionLabel}</Text></View>
          <Pressable accessibilityLabel="Apri il profilo" onPress={() => setScreen("profile")} style={[styles.avatar, screen === "profile" && styles.avatarSelected]}><Text style={styles.avatarText}>{session.user.name.charAt(0).toUpperCase()}</Text></Pressable>
        </View>
      </View>

      {screen === "profile" ? (
        <ProfileScreen session={session} onBack={() => setScreen("dashboard")} onPassword={() => setScreen("password")} onSettings={() => setScreen("settings")} onLogout={onLogout} />
      ) : screen === "password" ? (
        <ChangePasswordScreen token={session.access_token} onBack={() => setScreen("profile")} />
      ) : screen === "settings" ? (
        <SettingsScreen onBack={() => setScreen("profile")} />
      ) : (
      <ScrollView contentContainerStyle={styles.dashboardContent}>
        <View>
          <Text style={styles.welcome}>Ciao, {session.user.name.split(" ")[0]}</Text>
          <Text style={styles.roleCaption}>{roleLabel} · {session.user.role === "doctor" ? "Gestisci i pazienti associati" : "Il tuo monitoraggio posturale"}</Text>
        </View>

        {session.user.role === "doctor" && !selectedPatient ? (
          <DoctorPatientDirectory
            patients={doctorPatients}
            loading={patientsLoading}
            email={associationEmail}
            onEmailChange={setAssociationEmail}
            associating={associating}
            onAssociate={associatePatient}
            onSelect={setSelectedPatient}
          />
        ) : !latest || !posture ? (
          <>
            {session.user.role === "doctor" && <Pressable onPress={() => setSelectedPatient(null)} style={styles.patientStrip}><Text style={styles.backArrow}>‹</Text><View style={{ flex: 1 }}><Text style={styles.overline}>PAZIENTE SELEZIONATO</Text><Text style={styles.patientName}>{selectedPatient?.name}</Text></View><Text style={styles.patientCode}>{selectedPatient?.patient_code}</Text></Pressable>}
            <View style={styles.waitingCard}><ActivityIndicator color="#087f6a" size="large" /><Text style={styles.waitingTitle}>Nessun dato in tempo reale</Text><Text style={styles.muted}>Questo paziente non ha ancora un dispositivo attivo.</Text></View>
          </>
        ) : (
          <>
            {session.user.role === "doctor" && (
              <Pressable onPress={() => setSelectedPatient(null)} style={styles.patientStrip}><Text style={styles.backArrow}>‹</Text><View style={{ flex: 1 }}><Text style={styles.overline}>PAZIENTE SELEZIONATO</Text><Text style={styles.patientName}>{selectedPatient?.name}</Text></View><Text style={styles.patientCode}>{selectedPatient?.patient_code}</Text></Pressable>
            )}
            <View style={[styles.postureCard, { backgroundColor: posture.pale }]}>
              <View style={styles.postureTop}><View style={[styles.statusMark, { backgroundColor: posture.color }]}><Text style={styles.statusMarkText}>S</Text></View><View style={{ flex: 1 }}><Text style={[styles.postureLabel, { color: posture.color }]}>{posture.label}</Text><Text style={styles.postureDetail}>{posture.detail}</Text></View></View>
              <View style={styles.deviationRow}><Text style={styles.deviationCaption}>DEVIAZIONE DAL RIFERIMENTO</Text><Text style={[styles.deviationValue, { color: posture.color }]}>{formatSigned(latest.deviation_deg)}</Text></View>
            </View>
            <View style={styles.metricsRow}>
              <Metric label="Pitch" value={formatSigned(latest.pitch_deg)} />
              <Metric label="Roll" value={formatSigned(latest.roll_deg)} />
              <Metric label="Durata" value={`${latest.deviation_duration_seconds.toFixed(0)} s`} />
            </View>
            <View style={styles.whiteCard}>
              <View style={styles.sectionHeading}><View><Text style={styles.sectionTitle}>Andamento recente</Text><Text style={styles.mutedSmall}>Ultimi {visibleSamples.length} campioni · gradi</Text></View><View style={styles.legendDot}><View style={styles.miniDot} /><Text style={styles.legendText}>Deviazione</Text></View></View>
              <LineChart data={chartData} width={Math.max(280, width - 56)} height={190} withDots={false} withOuterLines={false} yAxisSuffix="°" chartConfig={{ backgroundGradientFrom: "#fff", backgroundGradientTo: "#fff", decimalPlaces: 0, color: (opacity = 1) => `rgba(8,127,106,${opacity})`, labelColor: (opacity = 1) => `rgba(71,84,103,${opacity})`, propsForBackgroundLines: { stroke: "#e4eeeb", strokeDasharray: "4 4" } }} bezier style={styles.chart} />
            </View>
            <View style={styles.infoGrid}>
              <InfoCard icon="▣" label="Dispositivo" value={latest.device_id} />
              <InfoCard icon="ϟ" label="Batteria" value={device?.state_of_charge != null ? `${Math.round(device.state_of_charge)}%` : "—"} />
            </View>
            {session.user.role === "patient" && (
              <Pressable onPress={calibrate} disabled={calibrating} style={({ pressed }) => [styles.primaryButton, pressed && styles.pressed]}>{calibrating ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Calibra postura di riferimento</Text>}</Pressable>
            )}
          </>
        )}
        {message ? <Text style={styles.message}>{message}</Text> : null}
        <Text style={styles.disclaimer}>Soglie dimostrative, non validate per uso clinico.</Text>
      </ScrollView>
      )}
    </SafeAreaView>
  );
}

function ProfileScreen({
  session, onBack, onPassword, onSettings, onLogout,
}: {
  session: Session; onBack: () => void; onPassword: () => void; onSettings: () => void; onLogout: () => void;
}) {
  const user = session.user;
  const firstName = user.first_name || user.name.split(" ")[0] || "—";
  const lastName = user.last_name || user.name.split(" ").slice(1).join(" ") || "—";

  function confirmLogout() {
    Alert.alert("Disconnetti account", "Vuoi davvero uscire da SmartBack?", [
      { text: "Annulla", style: "cancel" },
      { text: "Esci", style: "destructive", onPress: onLogout },
    ]);
  }

  return (
    <ScrollView contentContainerStyle={styles.pageContent}>
      <PageHeading title="Informazioni personali" subtitle="Il tuo profilo SmartBack" onBack={onBack} />
      <View style={styles.profileHero}>
        <View style={styles.profileAvatar}><Text style={styles.profileAvatarText}>{firstName.charAt(0).toUpperCase()}</Text></View>
        <Text style={styles.profileName}>{firstName} {lastName}</Text>
        <Text style={styles.profileRole}>{user.role === "doctor" ? "Medico" : "Paziente"}</Text>
      </View>
      <View style={styles.profileCard}>
        <ProfileInfo label="NOME" value={firstName} />
        <ProfileInfo label="COGNOME" value={lastName} />
        <ProfileInfo label="EMAIL" value={user.email} last />
      </View>
      <View style={styles.profileMenu}>
        <MenuButton icon="✦" title="Cambia password" subtitle="Aggiorna la password di accesso" onPress={onPassword} />
        <MenuButton icon="⚙" title="Impostazioni" subtitle="Preferenze dell'applicazione" onPress={onSettings} />
        <MenuButton icon="↪" title="Esci dall'account" subtitle="Torna alla schermata di accesso" onPress={confirmLogout} danger last />
      </View>
    </ScrollView>
  );
}

function ChangePasswordScreen({ token, onBack }: { token: string; onBack: () => void }) {
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
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.pageContent}>
        <PageHeading title="Cambia password" subtitle="Proteggi il tuo account" onBack={onBack} />
        <View style={styles.formCard}>
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

function SettingsScreen({ onBack }: { onBack: () => void }) {
  return (
    <ScrollView contentContainerStyle={styles.pageContent}>
      <PageHeading title="Impostazioni" subtitle="Personalizza la tua esperienza" onBack={onBack} />
      <View style={styles.settingsCard}>
        <View style={styles.settingIcon}><Text style={styles.settingIconText}>☼</Text></View>
        <View style={styles.settingCopy}><Text style={styles.settingTitle}>Tema dell'app</Text><Text style={styles.settingText}>Questa preferenza sarà disponibile in un prossimo aggiornamento.</Text></View>
        <View style={styles.soonBadge}><Text style={styles.soonText}>PROSSIMAMENTE</Text></View>
      </View>
      <Text style={styles.settingsNote}>In questa sezione aggiungeremo progressivamente le preferenze personali dell'applicazione.</Text>
    </ScrollView>
  );
}

function PageHeading({ title, subtitle, onBack }: { title: string; subtitle: string; onBack: () => void }) {
  return <View style={styles.pageHeading}><Pressable accessibilityLabel="Torna indietro" onPress={onBack} style={styles.backButton}><Text style={styles.backButtonText}>‹</Text></Pressable><View style={styles.pageHeadingCopy}><Text style={styles.pageTitle}>{title}</Text><Text style={styles.pageSubtitle}>{subtitle}</Text></View></View>;
}

function ProfileInfo({ label, value, last = false }: { label: string; value: string; last?: boolean }) {
  return <View style={[styles.profileInfo, last && styles.profileInfoLast]}><Text style={styles.profileInfoLabel}>{label}</Text><Text style={styles.profileInfoValue}>{value}</Text></View>;
}

function MenuButton({ icon, title, subtitle, onPress, danger = false, last = false }: { icon: string; title: string; subtitle: string; onPress: () => void; danger?: boolean; last?: boolean }) {
  return <Pressable onPress={onPress} style={({ pressed }) => [styles.menuButton, last && styles.menuButtonLast, pressed && styles.menuButtonPressed]}><View style={[styles.menuIcon, danger && styles.menuIconDanger]}><Text style={[styles.menuIconText, danger && styles.menuDangerText]}>{icon}</Text></View><View style={styles.menuCopy}><Text style={[styles.menuTitle, danger && styles.menuDangerText]}>{title}</Text><Text style={styles.menuSubtitle}>{subtitle}</Text></View><Text style={[styles.menuChevron, danger && styles.menuDangerText]}>›</Text></Pressable>;
}

function DoctorPatientDirectory({
  patients, loading, email, onEmailChange, associating, onAssociate, onSelect,
}: {
  patients: DoctorPatient[]; loading: boolean; email: string;
  onEmailChange: (value: string) => void; associating: boolean;
  onAssociate: () => void; onSelect: (patient: DoctorPatient) => void;
}) {
  return (
    <>
      <View style={styles.associationCard}>
        <View style={styles.associationHeading}>
          <View style={styles.addCircle}><Text style={styles.addSymbol}>+</Text></View>
          <View style={{ flex: 1 }}><Text style={styles.sectionTitle}>Associa un paziente</Text><Text style={styles.mutedSmall}>Usa l’email con cui il paziente si è registrato</Text></View>
        </View>
        <Field label="EMAIL DEL PAZIENTE" value={email} onChangeText={onEmailChange} keyboardType="email-address" autoCapitalize="none" placeholder="paziente@email.it" />
        <Pressable disabled={associating} onPress={onAssociate} style={({ pressed }) => [styles.associateButton, pressed && styles.pressed]}>
          {associating ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Aggiungi alla lista</Text>}
        </Pressable>
      </View>

      <View style={styles.directoryHeader}>
        <Text style={styles.directoryTitle}>I miei pazienti</Text>
        <View style={styles.countBadge}><Text style={styles.countText}>{patients.length}</Text></View>
      </View>
      {loading ? (
        <ActivityIndicator style={{ marginVertical: 32 }} color="#087f6a" size="large" />
      ) : patients.length === 0 ? (
        <View style={styles.emptyPatients}><Text style={styles.emptyIcon}>◎</Text><Text style={styles.waitingTitle}>Nessun paziente associato</Text><Text style={styles.emptyText}>Aggiungi un paziente tramite email per visualizzarlo qui.</Text></View>
      ) : patients.map((patient) => (
        <Pressable key={patient.id} onPress={() => onSelect(patient)} style={({ pressed }) => [styles.patientCard, pressed && styles.patientCardPressed]}>
          <View style={styles.patientAvatar}><Text style={styles.patientAvatarText}>{patient.name.charAt(0).toUpperCase()}</Text></View>
          <View style={{ flex: 1 }}><Text style={styles.patientCardName}>{patient.name}</Text><Text style={styles.patientEmail}>{patient.email}</Text><Text style={styles.patientCode}>{patient.patient_code}</Text></View>
          <View style={styles.patientCardRight}>{patient.has_live_data && <View style={styles.onlineBadge}><View style={styles.miniDot} /><Text style={styles.onlineText}>Live</Text></View>}<Text style={styles.chevron}>›</Text></View>
        </Pressable>
      ))}
    </>
  );
}

function Logo({ large = false }: { large?: boolean }) {
  return <SmartBackLogo large={large} />;
}

function Field(props: React.ComponentProps<typeof TextInput> & { label: string }) {
  const { label, ...inputProps } = props;
  const [focused, setFocused] = useState(false);
  return <View style={styles.field}><Text style={styles.inputLabel}>{label}</Text><TextInput {...inputProps} onFocus={(event) => { setFocused(true); inputProps.onFocus?.(event); }} onBlur={(event) => { setFocused(false); inputProps.onBlur?.(event); }} placeholderTextColor="#98aaa5" style={[styles.input, focused && styles.inputFocused, inputProps.style]} /></View>;
}

function RoleButton({ selected, label, onPress }: { selected: boolean; label: string; onPress: () => void }) {
  return <Pressable onPress={onPress} style={[styles.roleButton, selected && styles.roleButtonSelected]}><Text style={[styles.roleText, selected && styles.roleTextSelected]}>{label}</Text></Pressable>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <View style={styles.metricCard}><Text style={styles.metricLabel}>{label}</Text><Text style={styles.metricValue}>{value}</Text></View>;
}

function InfoCard({ icon, label, value }: { icon: string; label: string; value: string }) {
  return <View style={styles.infoCard}><Text style={styles.infoIcon}>{icon}</Text><View style={{ flex: 1 }}><Text style={styles.metricLabel}>{label}</Text><Text numberOfLines={1} style={styles.infoValue}>{value}</Text></View></View>;
}

function formatSigned(value: number) { return `${value > 0 ? "+" : ""}${value.toFixed(1)}°`; }

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
  headerBrand: { color: "#123c34", fontSize: 23, lineHeight: 27, fontWeight: "900", letterSpacing: -0.8 },
  headerRight: { flexDirection: "row", alignItems: "center", gap: 10 }, liveBadge: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#edf8f5", paddingHorizontal: 9, paddingVertical: 7, borderRadius: 18 }, liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#12b76a" }, liveDotOffline: { backgroundColor: "#98a2b3" }, liveText: { color: "#42655f", fontSize: 10, fontWeight: "800" },
  avatar: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#c8eee6", alignItems: "center", justifyContent: "center", borderWidth: 2, borderColor: "transparent" }, avatarSelected: { borderColor: "#087f6a", backgroundColor: "#e3f7f2" }, avatarText: { color: "#087f6a", fontWeight: "900" }, dashboardContent: { padding: 18, paddingBottom: 38, gap: 14 },
  welcome: { color: "#153d35", fontSize: 24, fontWeight: "900", letterSpacing: -0.5 }, roleCaption: { color: "#6b817c", marginTop: 3, fontSize: 12 }, waitingCard: { minHeight: 260, borderRadius: 24, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", gap: 10, padding: 24 }, waitingTitle: { color: "#153d35", fontSize: 18, fontWeight: "800" }, muted: { color: "#6b817c", fontSize: 12 },
  patientStrip: { backgroundColor: "#dff4ef", borderRadius: 16, padding: 14, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, overline: { color: "#438579", fontSize: 8, fontWeight: "900", letterSpacing: 1 }, patientName: { color: "#153d35", fontWeight: "800", marginTop: 3 }, patientCode: { color: "#5f817a", fontSize: 9 },
  postureCard: { padding: 18, borderRadius: 22, gap: 20 }, postureTop: { flexDirection: "row", gap: 13, alignItems: "flex-start" }, statusMark: { width: 43, height: 43, borderRadius: 22, alignItems: "center", justifyContent: "center" }, statusMarkText: { color: "#fff", fontWeight: "900", fontSize: 18 }, postureLabel: { fontSize: 19, fontWeight: "900" }, postureDetail: { color: "#526d67", fontSize: 12, lineHeight: 18, marginTop: 3 },
  deviationRow: { borderTopWidth: 1, borderTopColor: "rgba(30,70,60,.12)", paddingTop: 14, flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between" }, deviationCaption: { color: "#66817b", fontSize: 8, fontWeight: "900", letterSpacing: 0.7, flex: 1 }, deviationValue: { fontSize: 33, lineHeight: 37, fontWeight: "900", letterSpacing: -1 },
  metricsRow: { flexDirection: "row", gap: 9 }, metricCard: { flex: 1, backgroundColor: "#fff", padding: 13, borderRadius: 15 }, metricLabel: { color: "#78908a", fontSize: 10, fontWeight: "700" }, metricValue: { color: "#153d35", fontSize: 18, fontWeight: "900", marginTop: 4 },
  whiteCard: { backgroundColor: "#fff", borderRadius: 21, paddingTop: 17, overflow: "hidden" }, sectionHeading: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", paddingHorizontal: 17 }, sectionTitle: { color: "#153d35", fontSize: 16, fontWeight: "900" }, mutedSmall: { color: "#78908a", fontSize: 10, marginTop: 3 }, legendDot: { flexDirection: "row", alignItems: "center", gap: 5 }, miniDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#087f6a" }, legendText: { color: "#78908a", fontSize: 9 }, chart: { marginLeft: -13, marginTop: 8 },
  infoGrid: { flexDirection: "row", gap: 9 }, infoCard: { flex: 1, backgroundColor: "#fff", borderRadius: 16, padding: 13, flexDirection: "row", alignItems: "center", gap: 9 }, infoIcon: { color: "#20a38c", fontSize: 20 }, infoValue: { color: "#153d35", fontWeight: "800", fontSize: 12, marginTop: 3 },
  notificationCard: { backgroundColor: "#dff5f0", borderRadius: 17, padding: 14, flexDirection: "row", alignItems: "center", gap: 12 }, bellCircle: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#b9e9df", alignItems: "center", justifyContent: "center" }, bell: { color: "#087f6a", fontSize: 17 }, notificationTitle: { color: "#153d35", fontWeight: "900", fontSize: 13 }, notificationText: { color: "#56766f", fontSize: 10, lineHeight: 15, marginTop: 2 }, message: { color: "#42655f", textAlign: "center", fontSize: 11 }, disclaimer: { color: "#8ba09b", textAlign: "center", fontSize: 9, marginTop: 4 },
  associationCard: { backgroundColor: "#fff", borderRadius: 21, padding: 17 }, associationHeading: { flexDirection: "row", alignItems: "center", gap: 11 }, addCircle: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#dff5f0", alignItems: "center", justifyContent: "center" }, addSymbol: { color: "#087f6a", fontSize: 25, lineHeight: 27, fontWeight: "500" }, associateButton: { minHeight: 47, borderRadius: 14, backgroundColor: "#087f6a", alignItems: "center", justifyContent: "center", marginTop: 13 },
  directoryHeader: { flexDirection: "row", alignItems: "center", gap: 8, marginTop: 5 }, directoryTitle: { color: "#153d35", fontSize: 19, fontWeight: "900" }, countBadge: { minWidth: 25, height: 25, paddingHorizontal: 7, borderRadius: 13, backgroundColor: "#cceee7", alignItems: "center", justifyContent: "center" }, countText: { color: "#087f6a", fontSize: 11, fontWeight: "900" },
  emptyPatients: { minHeight: 210, borderRadius: 21, backgroundColor: "#fff", alignItems: "center", justifyContent: "center", padding: 28 }, emptyIcon: { color: "#64b9aa", fontSize: 38, marginBottom: 8 }, emptyText: { color: "#78908a", fontSize: 12, textAlign: "center", lineHeight: 18, marginTop: 5 },
  patientCard: { minHeight: 84, borderRadius: 18, backgroundColor: "#fff", padding: 14, flexDirection: "row", alignItems: "center", gap: 12, borderWidth: 1, borderColor: "#e0ece9" }, patientCardPressed: { backgroundColor: "#edf8f5", borderColor: "#9cd8cc" }, patientAvatar: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#cceee7", alignItems: "center", justifyContent: "center" }, patientAvatarText: { color: "#087f6a", fontSize: 19, fontWeight: "900" }, patientCardName: { color: "#153d35", fontSize: 15, fontWeight: "900" }, patientEmail: { color: "#67817b", fontSize: 11, marginTop: 2 }, patientCardRight: { alignItems: "flex-end", gap: 8 }, onlineBadge: { flexDirection: "row", alignItems: "center", gap: 4, borderRadius: 10, backgroundColor: "#e4f7ee", paddingHorizontal: 7, paddingVertical: 4 }, onlineText: { color: "#087f6a", fontSize: 8, fontWeight: "900" }, chevron: { color: "#5e8f85", fontSize: 25, lineHeight: 25 }, backArrow: { color: "#087f6a", fontSize: 28, lineHeight: 30, marginRight: 8 },
  pageContent: { flexGrow: 1, padding: 18, paddingBottom: 42, gap: 16 }, pageHeading: { flexDirection: "row", alignItems: "center", gap: 12, marginBottom: 2 }, backButton: { width: 42, height: 42, borderRadius: 21, backgroundColor: "#fff", borderWidth: 1, borderColor: "#dceae6", alignItems: "center", justifyContent: "center" }, backButtonText: { color: "#087f6a", fontSize: 30, lineHeight: 31, marginTop: -2 }, pageHeadingCopy: { flex: 1 }, pageTitle: { color: "#153d35", fontSize: 23, fontWeight: "900", letterSpacing: -0.5 }, pageSubtitle: { color: "#6b817c", fontSize: 12, marginTop: 2 },
  profileHero: { alignItems: "center", backgroundColor: "#dff4ef", borderRadius: 24, paddingVertical: 24, paddingHorizontal: 18 }, profileAvatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: "#087f6a", alignItems: "center", justifyContent: "center", shadowColor: "#064b3f", shadowOpacity: 0.16, shadowRadius: 10, shadowOffset: { width: 0, height: 5 }, elevation: 4 }, profileAvatarText: { color: "#fff", fontSize: 29, fontWeight: "900" }, profileName: { color: "#153d35", fontSize: 21, fontWeight: "900", marginTop: 12 }, profileRole: { color: "#087f6a", fontSize: 11, fontWeight: "800", marginTop: 4, textTransform: "uppercase", letterSpacing: 0.8 },
  profileCard: { backgroundColor: "#fff", borderRadius: 21, paddingHorizontal: 17 }, profileInfo: { paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: "#e6efed" }, profileInfoLast: { borderBottomWidth: 0 }, profileInfoLabel: { color: "#78908a", fontSize: 9, fontWeight: "900", letterSpacing: 0.8 }, profileInfoValue: { color: "#153d35", fontSize: 15, fontWeight: "700", marginTop: 4 },
  profileMenu: { backgroundColor: "#fff", borderRadius: 21, paddingHorizontal: 15 }, menuButton: { minHeight: 72, flexDirection: "row", alignItems: "center", gap: 12, borderBottomWidth: 1, borderBottomColor: "#e6efed" }, menuButtonLast: { borderBottomWidth: 0 }, menuButtonPressed: { opacity: 0.65 }, menuIcon: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#dff5f0", alignItems: "center", justifyContent: "center" }, menuIconDanger: { backgroundColor: "#fee9e7" }, menuIconText: { color: "#087f6a", fontSize: 17, fontWeight: "900" }, menuDangerText: { color: "#b42318" }, menuCopy: { flex: 1 }, menuTitle: { color: "#153d35", fontSize: 14, fontWeight: "900" }, menuSubtitle: { color: "#78908a", fontSize: 10, marginTop: 3 }, menuChevron: { color: "#6f9189", fontSize: 26 },
  formCard: { backgroundColor: "#fff", borderRadius: 23, padding: 19 }, passwordHint: { color: "#78908a", fontSize: 10, lineHeight: 15, marginTop: 11 }, settingsCard: { backgroundColor: "#fff", borderRadius: 21, padding: 17, flexDirection: "row", alignItems: "center", gap: 12 }, settingIcon: { width: 45, height: 45, borderRadius: 23, backgroundColor: "#dff5f0", alignItems: "center", justifyContent: "center" }, settingIconText: { color: "#087f6a", fontSize: 22 }, settingCopy: { flex: 1 }, settingTitle: { color: "#153d35", fontSize: 15, fontWeight: "900" }, settingText: { color: "#78908a", fontSize: 10, lineHeight: 15, marginTop: 3 }, soonBadge: { backgroundColor: "#edf4f2", borderRadius: 10, paddingHorizontal: 7, paddingVertical: 5 }, soonText: { color: "#608078", fontSize: 7, fontWeight: "900", letterSpacing: 0.4 }, settingsNote: { color: "#78908a", fontSize: 11, lineHeight: 17, textAlign: "center", paddingHorizontal: 18 },
});

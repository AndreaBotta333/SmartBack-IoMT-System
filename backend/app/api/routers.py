"""Router dei domini applicativi e relative sezioni OpenAPI.

I router mantengono intenzionalmente i percorsi pubblici completi nei moduli
degli endpoint. La separazione rimane così interna e documentale, senza
modificare il contratto API già usato dall'app mobile, da Grafana e dai servizi
dei dispositivi.
"""

from fastapi import APIRouter


OPENAPI_TAGS = [
    {"name": "Sistema", "description": "Stato del servizio e controlli di funzionamento."},
    {"name": "App · Autenticazione", "description": "Registrazione, accesso e gestione dell'account di pazienti e medici."},
    {"name": "App · Medico", "description": "Pazienti seguiti dal medico e configurazione del monitoraggio."},
    {"name": "Monitoraggio · Diurno", "description": "Dati posturali in tempo reale, storico e statistiche diurne."},
    {"name": "Monitoraggio · Notturno", "description": "Attivazione, stato, posizioni e storico del monitoraggio notturno."},
    {"name": "Dispositivi", "description": "Stato della smart shirt e operazioni di calibrazione."},
    {"name": "Grafana · Portale medico", "description": "API autenticate riservate al portale medico e alle dashboard Grafana."},
    {"name": "Tempo reale", "description": "Flussi WebSocket destinati ai client interattivi."},
]

system_router = APIRouter(tags=["Sistema"])
auth_router = APIRouter(tags=["App · Autenticazione"])
doctor_router = APIRouter(tags=["App · Medico"])
day_monitoring_router = APIRouter(tags=["Monitoraggio · Diurno"])
night_monitoring_router = APIRouter(tags=["Monitoraggio · Notturno"])
devices_router = APIRouter(tags=["Dispositivi"])
grafana_router = APIRouter(tags=["Grafana · Portale medico"])
grafana_pages_router = APIRouter(include_in_schema=False)
realtime_router = APIRouter(tags=["Tempo reale"])


OPENAPI_SUMMARIES = {
    ("get", "/"): "Informazioni sul servizio",
    ("get", "/health"): "Verifica lo stato del sistema",
    ("post", "/api/v1/auth/register"): "Registra un nuovo account",
    ("post", "/api/v1/auth/login"): "Accedi all'app",
    ("get", "/api/v1/auth/me"): "Mostra il profilo corrente",
    ("post", "/api/v1/auth/logout"): "Termina la sessione dell'app",
    ("post", "/api/v1/notifications/token"): "Registra il dispositivo per le notifiche push",
    ("delete", "/api/v1/notifications/token"): "Rimuove il dispositivo dalle notifiche push",
    ("get", "/api/v1/notifications"): "Elenca le notifiche dell'utente",
    ("delete", "/api/v1/notifications"): "Cancella le notifiche dell'utente",
    ("post", "/api/v1/notifications/test"): "Invia una notifica di prova",
    ("delete", "/api/v1/auth/account"): "Elimina l'account corrente",
    ("put", "/api/v1/auth/password"): "Modifica la password",
    ("put", "/api/v1/auth/avatar"): "Modifica l'immagine del profilo",
    ("get", "/api/v1/doctor/patients"): "Elenca i pazienti seguiti",
    ("post", "/api/v1/doctor/patients"): "Associa un paziente al medico",
    ("get", "/api/v1/doctor/patients/{patient_id}/monitoring-config"): "Mostra la configurazione del monitoraggio",
    ("put", "/api/v1/doctor/patients/{patient_id}/monitoring-config"): "Aggiorna la configurazione del monitoraggio",
    ("delete", "/api/v1/doctor/patients/{patient_id}/monitoring-config"): "Ripristina la configurazione del monitoraggio",
    ("get", "/api/v1/posture/latest"): "Mostra l'ultima rilevazione posturale",
    ("get", "/api/v1/posture/history"): "Mostra lo storico posturale",
    ("get", "/api/v1/posture/history/availability"): "Verifica la disponibilità dello storico",
    ("get", "/api/v1/patient/statistics"): "Mostra le statistiche del paziente",
    ("post", "/api/v1/night-monitoring/start"): "Avvia il monitoraggio notturno",
    ("post", "/api/v1/night-monitoring/stop"): "Termina il monitoraggio notturno",
    ("get", "/api/v1/night-monitoring/status"): "Mostra lo stato del monitoraggio notturno",
    ("get", "/api/v1/night-monitoring/history"): "Mostra lo storico notturno",
    ("get", "/api/v1/night-monitoring/sessions/{session_id}"): "Mostra una sessione notturna",
    ("get", "/api/v1/device/latest"): "Mostra lo stato più recente della smart shirt",
    ("post", "/api/v1/devices/{device_id}/calibration"): "Calibra la smart shirt",
    ("post", "/api/v1/grafana/login"): "Accedi al portale medico",
    ("get", "/api/v1/grafana/home"): "Mostra i dati della Home medica",
    ("post", "/api/v1/grafana/patients"): "Associa un paziente da Grafana",
    ("delete", "/api/v1/grafana/patients/{patient_code}"): "Rimuove un paziente dal portale medico",
    ("post", "/api/v1/grafana/devices"): "Aggiunge una smart shirt",
    ("delete", "/api/v1/grafana/devices/{device_id}"): "Rimuove una smart shirt",
    ("put", "/api/v1/grafana/devices/{device_id}/assignment"): "Assegna una smart shirt",
    ("delete", "/api/v1/grafana/devices/{device_id}/assignment"): "Libera una smart shirt",
    ("get", "/api/v1/grafana/auth"): "Verifica la sessione del portale medico",
    ("post", "/api/v1/grafana/token-rotation"): "Aggiorna la sessione Grafana",
    ("post", "/api/v1/grafana/patients/{patient_code}/calibration"): "Calibra la postura del paziente",
    ("post", "/api/v1/grafana/patients/{patient_code}/calibration-snapshot"): "Acquisisce i valori per la calibrazione",
    ("post", "/api/v1/grafana/patients/{patient_code}/calibration-form"): "Conferma la calibrazione acquisita",
    ("post", "/api/v1/grafana/patients/{patient_code}/manual-calibration"): "Imposta manualmente la calibrazione",
    ("get", "/api/v1/grafana/patients/{patient_code}/night-monitoring/status"): "Mostra lo stato notturno nel portale medico",
    ("post", "/api/v1/grafana/patients/{patient_code}/night-monitoring/start"): "Avvia il monitoraggio notturno dal portale medico",
    ("post", "/api/v1/grafana/patients/{patient_code}/night-monitoring/stop"): "Termina il monitoraggio notturno dal portale medico",
    ("post", "/api/v1/grafana/logout"): "Termina la sessione del portale medico",
}

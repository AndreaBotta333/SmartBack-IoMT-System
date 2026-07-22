# Organizzazione delle API SmartBack

Gli endpoint mantengono i percorsi pubblici esistenti, ma sono registrati con
router separati per dominio. La stessa suddivisione è visibile nella pagina
OpenAPI `/docs`.

| Sezione OpenAPI | Consumer principale | Responsabilità |
| --- | --- | --- |
| `Sistema` | Docker e strumenti operativi | informazioni sul servizio e stato del sistema |
| `App · Autenticazione` | app mobile | registrazione, accesso e profilo |
| `App · Medico` | app del medico | pazienti e configurazione del monitoraggio |
| `Monitoraggio · Diurno` | app e servizi clinici | tempo reale, storico e statistiche posturali |
| `Monitoraggio · Notturno` | app e servizi clinici | attivazione, stato e storico notturno |
| `Dispositivi` | app e integrazione maglia | stato del dispositivo e calibrazione |
| `Grafana · Portale medico` | gateway Grafana e portale medico | inventario, assegnazioni e controlli delle dashboard |
| `Tempo reale` | app mobile | flussi WebSocket dei dati wearable |

Le pagine HTML interne usate dal portale e dai pannelli incorporati di Grafana
sono instradate separatamente e non vengono mostrate come API pubbliche in
OpenAPI. Questo evita che controlli di interfaccia e contratti destinati
all'app vengano confusi tra loro.

I router sono dichiarati in `backend/app/api/routers.py`. Ogni nuovo endpoint
deve essere aggiunto al router del proprio dominio; non va registrato
direttamente sull'istanza globale FastAPI.

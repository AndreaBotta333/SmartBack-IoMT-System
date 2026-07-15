# Registro modifiche SmartBack

Registro cronologico temporaneo dello sviluppo. Le voci più recenti vengono aggiunte in fondo al documento.

## Stato consolidato precedente al 15 luglio 2026

### Impostazione dell'architettura

- Predisposta l'infrastruttura Docker Compose del progetto.
- Configurati Mosquitto, InfluxDB, Node-RED, backend FastAPI, simulatore, Grafana e applicazione mobile Expo.
- Stabilito che ESP32 sarà utilizzato soltanto per la trasmissione dei dati, senza elaborazioni locali.
- Predisposto il simulatore per consentire lo sviluppo in assenza della smart t-shirt HOWDY Senior.
- Configurata l'app mobile per l'avvio manuale tramite attach di VS Code ed Expo in modalità LAN.

### Persistenza e autenticazione

- Implementata l'autenticazione con registrazione, accesso, sessioni e uscita.
- Utilizzato SQLite per utenti, credenziali, ruoli, sessioni e associazioni medico-paziente.
- Utilizzato InfluxDB per dati posturali e serie temporali del dispositivo.
- Configurati volumi Docker persistenti.
- Implementata la protezione delle password mediante PBKDF2 e salt.

### Ruoli e associazioni

- Distinti i ruoli Paziente e Medico.
- Implementata la registrazione specifica per ruolo.
- Aggiunti codice fiscale per il paziente e codice medico dimostrativo per il medico.
- Implementata l'associazione di più pazienti a uno stesso medico.
- Aggiunta la lista dei pazienti associati e la selezione del singolo paziente da monitorare.
- Accantonate temporaneamente le notifiche push.

### Validazioni

- Aggiunti controlli su nome, cognome, email, password, codice fiscale e codice medico.
- Impedita la registrazione duplicata della stessa email.
- Implementato il controllo formale e del carattere di controllo del codice fiscale italiano.
- Verificato il codice medico dimostrativo nel backend.

### Interfaccia mobile

- Aggiornata l'interfaccia con una palette sui toni del verde acqua.
- Aggiunta un'intestazione fissa nelle schermate operative.
- Evidenziati i campi di testo quando ricevono il focus.
- Resi riconoscibili i collegamenti Registrati e Accedi.
- Rimossi gli indicatori circolari dai pulsanti Paziente e Medico.
- Integrato il logo SmartBack fornito, rimuovendo lo sfondo e mantenendo il contenuto originale.
- Ridotto lo spazio tra il logo iniziale e la frase "La postura guidata dai dati".

## 15 luglio 2026 — Correzione logo e campo codice medico

### Obiettivo

Ridurre lo spazio sotto il logo nella schermata iniziale e rendere utilizzabile il campo Codice medico.

### Modifiche

- Tagliato il bordo trasparente inferiore del PNG del logo.
- Adeguata l'altezza del contenitore React Native del logo.
- Ridotto il margine superiore della frase sotto il logo.
- Assegnate identità distinte ai campi Codice fiscale e Codice medico.
- Reso esplicitamente editabile il campo Codice medico e disattivata la correzione automatica.

### File interessati

- `mobile/app/App.tsx`
- `mobile/app/SmartBackLogo.tsx`
- `mobile/app/assets/smartback-logo-transparent.png`

### Verifica

- Controllo TypeScript completato nel container mobile senza errori.

## 15 luglio 2026 — Aggiornamento configurazione di rete

### Obiettivo

Allineare Expo e i servizi mobile al nuovo indirizzo IP del computer.

### Modifiche

- Aggiornato `HOST_IP` nel file `.env`.
- Ricreato esclusivamente il container mobile.
- Verificati gli indirizzi del packager Expo, dell'API e del WebSocket nel container.

### Nota operativa

Dopo ogni cambio di rete occorre aggiornare `.env`, ricreare il container mobile, eseguire nuovamente l'attach di VS Code e riavviare Expo con cache pulita.

## 15 luglio 2026 — Validazioni obbligatorie ed email

### Obiettivo

Impedire registrazioni incomplete e rafforzare il controllo sintattico dell'indirizzo email.

### Modifiche

- Resi esplicitamente obbligatori sia Nome sia Cognome.
- Aggiunto un messaggio specifico quando uno dei due campi non è compilato.
- Rafforzata la sintassi email richiesta nel formato `nome@provider.dominio`.
- Applicati i controlli sia nell'app mobile sia nel backend.
- Ricostruito e riavviato il backend.

### File interessati

- `mobile/app/App.tsx`
- `backend/app/main.py`

### Verifica

- Controllo TypeScript completato senza errori.
- Controllo della sintassi Python completato senza errori.

## 15 luglio 2026 — Uniformazione dei messaggi in italiano

### Obiettivo

Assicurare che tutti i messaggi mostrati all'utente siano in italiano.

### Modifiche

- Tradotto il messaggio di credenziali errate in "Email o password non corrette".
- Tradotti i messaggi relativi ad autenticazione, sessione, campioni posturali e stato del dispositivo.
- Ricostruito e riavviato il backend.

### File interessati

- `backend/app/main.py`

## Regola per gli aggiornamenti successivi

Per ogni futuro intervento verrà aggiunta una nuova sezione contenente:

1. data e titolo sintetico;
2. obiettivo richiesto;
3. modifiche effettuate;
4. file e componenti interessati;
5. verifiche eseguite;
6. eventuali limiti o attività ancora aperte.

## 15 luglio 2026 — Preparazione della condivisione su GitHub

### Obiettivo

Rendere il progetto disponibile ai collaboratori tramite una repository GitHub condivisa.

### Modifiche

- Inizializzata una repository Git autonoma nella cartella `iomt-lab`.
- Collegato il remote `AndreaBotta333/SmartBack-IoMT-System`.
- Integrati il commit iniziale remoto, la licenza Apache 2.0 e il `.gitignore` esistente.
- Rimossa dalla struttura di lavoro la repository Git annidata di `mobile/app`, conservandone temporaneamente una copia di sicurezza esterna al progetto.
- Esteso `.gitignore` per escludere configurazioni locali, database, volumi Docker, dipendenze, cache e file di sistema.
- Creato `.env.example` come modello condivisibile per la configurazione locale.
- Creato il `README.md` principale con architettura, requisiti e procedura di avvio per i collaboratori.
- Spostate le credenziali locali di InfluxDB e Grafana dal codice versionato al file `.env` escluso da Git.

### File interessati

- `.gitignore`
- `.env.example`
- `README.md`
- `REPORT_TEMPORANEI/REGISTRO_MODIFICHE.md`

### Stato

- Repository locale collegata al remoto.
- Staging del primo commit applicativo preparato e controllato.
- Primo commit applicativo creato: `fa6a22a` (`feat: pubblica la struttura iniziale di SmartBack`).
- Push completato sul ramo remoto `origin/main`.
- Repository locale e repository GitHub sincronizzate.

## 15 luglio 2026 — Profilo personale, impostazioni e Safe Area

### Obiettivo

Migliorare l'impaginazione delle schermate operative e introdurre una navigazione personale distinta dal logout.

### Modifiche

- Integrata la Safe Area nativa di Expo per evitare sovrapposizioni con ora, batteria, notch e indicatori di sistema.
- Sostituito il logo nell'intestazione operativa con il solo nome testuale `SmartBack`.
- Trasformato l'avatar con iniziale in un pulsante che apre la pagina Informazioni personali.
- Aggiunta la pagina Profilo con nome, cognome, email e ruolo.
- Spostato il logout nella pagina Profilo, con richiesta di conferma prima della disconnessione.
- Aggiunta la pagina Cambia password con password attuale, nuova password e conferma.
- Implementato nel backend il cambio reale della password con verifica della password attuale e salvataggio PBKDF2 con nuovo salt.
- Aggiunta la pagina Impostazioni con una sezione predisposta per il futuro tema dell'app.
- Mantenuti tutti i testi visibili all'utente in italiano.

### File interessati

- `mobile/app/App.tsx`
- `mobile/app/package.json`
- `mobile/app/package-lock.json`
- `backend/app/main.py`
- `REPORT_TEMPORANEI/REGISTRO_MODIFICHE.md`

### Verifiche

- Controllo TypeScript completato senza errori.
- Controllo della sintassi Python completato senza errori.
- Bundle Android Expo generata correttamente, con 720 moduli elaborati.
- Backend attivo e in stato `ok`.
- Rotta `/api/v1/auth/password` presente nello schema OpenAPI.

### Attività aperte

- Verificare visivamente le nuove schermate su più modelli di telefono.
- Definire e implementare in seguito le preferenze effettive della pagina Impostazioni.

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

## 15 luglio 2026 — Riorganizzazione directory pazienti del Medico

### Obiettivo

Dare priorità alla lista dei pazienti associati, semplificare l'aggiunta di un paziente e alleggerire l'intestazione operativa.

### Modifiche

- Adeguata la scritta `SmartBack` nell'intestazione ai colori blu e ai pesi tipografici del logo originale.
- Rimosso il badge di connessione `Live` dall'intestazione, mantenendo l'avatar del profilo.
- Conservato il badge `Live` esclusivamente sulle schede dei pazienti attivi nella lista del Medico.
- Spostata la lista dei pazienti associati prima dei controlli di aggiunta.
- Mantenuto uno stato vuoto esplicito quando il Medico non ha pazienti associati.
- Aggiunto sotto la lista un pulsante `+ Associa un paziente`.
- Implementato un pannello espandibile per inserire il codice fiscale del paziente.
- Sostituita nel backend l'associazione tramite email con l'associazione tramite codice fiscale validato.

### File interessati

- `mobile/app/App.tsx`
- `backend/app/main.py`
- `REPORT_TEMPORANEI/REGISTRO_MODIFICHE.md`

### Verifiche

- Controllo TypeScript completato senza errori.
- Controllo della sintassi Python completato senza errori.
- Bundle Android Expo generata correttamente.
- Backend ricostruito e riavviato correttamente.

### Nota

Il paziente può essere associato soltanto se è già registrato e il codice fiscale inserito coincide con quello salvato nel suo profilo.

## 15 luglio 2026 — Storico posturale, statistiche e configurazioni cliniche

### Obiettivo

Integrare una vista storica per paziente, statistiche personali e parametri di monitoraggio configurabili dal Medico.

### Modifiche

- Aggiunto un grafico storico sotto il grafico in tempo reale.
- Aggiunta la selezione del periodo tra 1 ora, 6 ore, 24 ore e 7 giorni.
- Evidenziati in verde-acqua i campioni corretti e in rosso quelli classificati come scorretti.
- Reso lo storico disponibile al Paziente per i propri dati e al Medico per ogni paziente associato selezionato.
- Protetti gli endpoint affinché un Paziente non possa leggere dati altrui e un Medico possa leggere soltanto i pazienti associati.
- Aggiunte per il Paziente statistiche su percentuale corretta, percentuale scorretta, deviazione media e deviazione massima.
- Aggiunta per il Medico la gestione di soglia moderata, soglia marcata e tempo di persistenza per ciascun paziente.
- Creata in SQLite la tabella `monitoring_configs` per la persistenza delle configurazioni individuali.
- Collegata la configurazione individuale al calcolo posturale eseguito dal backend.
- Campionato lo storico InfluxDB in circa 240 punti per periodo, mantenendo il grafico leggibile anche su intervalli lunghi.
- Corretta la query InfluxDB per evitare punti duplicati generati dalle serie separate per stato posturale.

### File interessati

- `mobile/app/App.tsx`
- `backend/app/main.py`
- `REPORT_TEMPORANEI/REGISTRO_MODIFICHE.md`

### Verifiche

- Controllo TypeScript completato senza errori.
- Controllo della sintassi Python completato senza errori.
- Bundle Android Expo generata correttamente.
- Test integrato dello storico completato su dati InfluxDB reali del simulatore.
- Test integrato delle statistiche personali completato.
- Test GET e PUT delle configurazioni Medico completato con successo.
- Verificata la rimozione delle sessioni temporanee usate nei test.

### Note e limiti

- Le statistiche sono calcolate sui campioni aggregati del periodo selezionato.
- Le soglie iniziali restano dimostrative e non validate per uso clinico.
- I valori dovranno essere giustificati tramite fonti mediche e formalizzati nella futura documentazione tecnica.

## 15 luglio 2026 — Spiegazione e reset soglie, tema scuro

### Obiettivo

Rendere comprensibile la configurazione posturale, permettere il ripristino dei valori iniziali e aggiungere il tema scuro.

### Analisi delle fonti mediche

- Le fonti analizzate confermano che l'aumento della flessione cervicale incrementa progressivamente il carico sul collo.
- La revisione sul Text Neck riporta esempi biomeccanici a 15°, 30°, 45° e 60° di flessione.
- La revisione sugli esercizi correttivi riporta criteri angolari utilizzati in specifici protocolli, tra cui angolo della testa in avanti superiore a 46°.
- Lo studio sulla durata d'uso dello smartphone rileva differenze tra esposizioni di 10, 20 e 30 minuti.
- Queste misure non coincidono direttamente con la deviazione relativa dell'IMU rispetto alla postura calibrata.
- Le fonti non giustificano direttamente la persistenza di 5 secondi.
- Per questo motivo `10° / 20° / 5 s` restano definiti valori predefiniti di progetto e non cut-off diagnostici o clinicamente validati.

### Modifiche

- Aggiunta nel pannello Medico una spiegazione della soglia moderata, della soglia marcata e della persistenza.
- Aggiunto il pulsante `Ripristina predefiniti` con conferma preventiva.
- Implementato l'endpoint backend `DELETE` che elimina la configurazione personalizzata del paziente e ripristina `10° / 20° / 5 s`.
- Implementato il toggle Tema scuro nella pagina Impostazioni.
- Salvata la preferenza del tema tramite Expo SecureStore, mantenendola dopo la chiusura dell'app.
- Applicato il tema scuro a schermate di accesso, dashboard, profilo, impostazioni, moduli, liste, statistiche e grafici.

### File interessati

- `mobile/app/App.tsx`
- `backend/app/main.py`
- `REPORT_TEMPORANEI/REGISTRO_MODIFICHE.md`

### Verifiche

- Controllo TypeScript completato senza errori.
- Controllo della sintassi Python completato senza errori.
- Bundle Android Expo generata correttamente.
- Backend ricostruito e riavviato.
- Endpoint di reset testato: restituiti correttamente `10.0 / 20.0 / 5.0`.
- Sessione temporanea di test eliminata.

### Attività aperta

- Definire soglie clinicamente motivate mediante uno studio di calibrazione che metta in relazione l'orientamento IMU della t-shirt con misure posturali anatomiche validate.

## 15 luglio 2026 — Avatar personali e semplificazione pannello soglie

### Obiettivo

Rendere gli avatar pertinenti agli utenti visualizzati, permettere la scelta di una foto profilo e rimuovere dal pannello Medico la spiegazione descrittiva delle soglie.

### Modifiche

- Rimossa dal pannello Medico la sezione `A cosa servono?`; i campi di configurazione e il ripristino dei valori predefiniti restano disponibili.
- Sostituita la lettera fissa `S` nel riquadro della deviazione con l'avatar del paziente effettivamente monitorato.
- Uniformati gli avatar nell'intestazione, nel profilo, nell'elenco pazienti e nel riquadro posturale.
- Mostrata l'iniziale corretta dell'utente quando non è stata impostata una foto.
- Aggiunto nella pagina delle informazioni personali il comando `Cambia foto`, con selezione dalla galleria e ritaglio quadrato.
- Aggiunta la dipendenza ufficiale Expo `expo-image-picker` compatibile con SDK 54.
- Aggiunto l'endpoint autenticato `PUT /api/v1/auth/avatar`.
- Aggiunta in SQLite la colonna persistente `avatar_data`, resa disponibile anche al medico per i pazienti associati.
- Limitate le foto ai formati JPEG/PNG e alla dimensione massima di 2 MB.
- Aggiornata la sessione locale dopo il salvataggio, così la nuova foto appare immediatamente e resta visibile ai successivi accessi.

### File interessati

- `mobile/app/App.tsx`
- `mobile/app/app.json`
- `mobile/app/package.json`
- `mobile/app/package-lock.json`
- `backend/app/main.py`
- `REPORT_TEMPORANEI/REGISTRO_MODIFICHE.md`

### Verifiche

- Controllo TypeScript completato senza errori.
- Controllo della sintassi Python completato senza errori.
- Bundle Android Expo generata correttamente.
- Backend ricostruito e riavviato correttamente.
- Migrazione SQLite verificata: la colonna `avatar_data` è presente e i 7 utenti esistenti sono rimasti invariati.
- Tutti i container applicativi risultano attivi.

## 20 luglio 2026 — Modalità notte e monitoraggio del decubito

### Obiettivo

Introdurre una modalità notturna attivabile dal Paziente, mostrare in tempo reale supino, prono e decubiti laterali nell'app e nelle dashboard Grafana dedicate, sincronizzando contestualmente il tema scuro.

### Modifiche

- Aggiunto nell'area Paziente il pulsante `MODALITÀ NOTTE`.
- L'avvio crea una sessione notturna persistente associata al Paziente e alla maglia assegnata; l'arresto la chiude mantenendone lo storico.
- Reso l'avvio e l'arresto disponibili esclusivamente al Paziente; il Medico associato può consultare i dati senza controllare la sessione.
- Attivato automaticamente il tema scuro all'avvio della modalità notte.
- Bloccata la disattivazione manuale del tema nelle Impostazioni finché il monitoraggio notturno è attivo.
- Sostituita durante la sessione notturna la dashboard posturale diurna con una vista live dedicata.
- Mostrate nell'app posizione corrente, durata della sessione, maglia utilizzata e tempi cumulati supino, prono, lato destro e lato sinistro.
- Gestiti gli eventi notturni ricevuti in tempo reale tramite il WebSocket già utilizzato dall'app.
- Aggiunta la classificazione backend indipendente delle posizioni `supine`, `prone`, `right_side`, `left_side` e `unknown` a partire dal vettore di gravità normalizzato.
- Aggiunti smoothing, isteresi e stabilizzazione temporale per limitare cambi di posizione dovuti a rumore o transizioni brevi.
- Persistiti i campioni notturni nella measurement InfluxDB separata `night_position`.
- Evitata la scrittura dei dati notturni nello storico posturale diurno quando una sessione notte è attiva.
- Aggiunte le dashboard Grafana separate per monitoraggio notturno live e storico notturno.
- Aggiunti i collegamenti alle dashboard notturne nella Home medica Grafana.
- Aggiunti endpoint autenticati per avvio, arresto, stato, storico e dettaglio delle sessioni notturne.
- Aggiunta la commutazione automatica della sola maglia simulata su `night-cycle` all'avvio e su `day-cycle` all'arresto.
- Confermato che l'ESP32 resta limitato alla trasmissione e non esegue classificazioni o calcoli.

### File principali interessati

- `mobile/app/App.tsx`
- `backend/app/main.py`
- `backend/app/database.py`
- `backend/app/night_service.py`
- `backend/app/influx_manager.py`
- `backend/app/mqtt_handler.py`
- `backend/tests/test_night_monitoring.py`
- `backend/tests/test_night_service.py`
- `simulator/simulator.py`
- `simulator/test_simulator.py`
- `grafana/dashboards/smartback-night.json`
- `grafana/dashboards/smartback-night-history.json`
- `docs/NIGHT_MONITORING.md`

### Verifiche

- Controllo TypeScript completato senza errori.
- Bundle Android Expo generato correttamente.
- 35 test backend completati con successo.
- 7 test del simulatore completati con successo.
- Verificata la classificazione di supino, prono, decubito destro, decubito sinistro e posizione incerta.
- Verificata l'autorizzazione Paziente/Medico sugli endpoint notturni.
- Verificata la commutazione automatica dello scenario per le sole maglie simulate.
- Validata la sintassi JSON di tutte le dashboard Grafana.

### Note e limiti

- La corrispondenza iniziale degli assi è coerente con il simulatore ma dovrà essere confermata sperimentalmente quando sarà disponibile la smart t-shirt fisica.
- La classificazione notturna è una misura tecnica della posizione della maglia e non costituisce una diagnosi clinica.

## 20 luglio 2026 — Semplificazione vista notturna

### Modifiche

- Rimossa dall'app Paziente la percentuale di affidabilità della classificazione.
- Rimossa dalla dashboard Grafana live la serie `Qualità della classificazione`.
- Esteso il grafico di distribuzione delle posizioni all'intera larghezza disponibile.
- Mantenuto il valore tecnico di affidabilità esclusivamente nel backend e in InfluxDB, senza esporlo nelle interfacce utente.
- Verificato il comportamento senza maglia assegnata: il backend blocca l'avvio, non crea alcuna sessione notturna e restituisce il messaggio `Nessuna maglia attiva assegnata al paziente`.
- Uniformata la dicitura della posizione corrente nell'app: `Lato destro` e `Lato sinistro`, coerentemente con i riepiloghi sottostanti.
- Uniformate tutte le etichette notturne in minuscolo: `supino`, `prono`, `lato destro`, `lato sinistro` e `transizione`.
- Resi fluidi i contatori notturni nell'app con aggiornamento ogni secondo, mantenendo un riallineamento periodico con i valori autorevoli del backend.
- Gestito il cambio posizione in tempo reale: l'incremento locale viene trasferito subito al nuovo stato senza attendere il successivo ciclo di polling di cinque secondi.
- Resa fluida anche la durata complessiva della sessione notturna.
- Ripristinate nell'app le diciture `decubito destro` e `decubito sinistro`.
- Allineati i colori delle posizioni nelle dashboard Grafana ai colori esatti utilizzati nell'app.
- Impostato il ritorno automatico al tema chiaro quando termina la modalità notte, anche se la chiusura viene rilevata dal successivo aggiornamento dello stato.

## 20 luglio 2026 — Ripristino monitoraggio notturno live in Grafana

### Problema individuato

- I campioni notturni arrivavano regolarmente in InfluxDB, ma la dashboard filtrava anche per la variabile `session_id`, che poteva rimanere vuota quando l'accesso avveniva dalla Home o tramite un collegamento contenente il solo paziente.

### Modifiche

- Rimossa la selezione manuale obbligatoria della sessione dalla dashboard live.
- Ogni pannello ricava automaticamente l'ultima sessione notturna disponibile per il paziente selezionato.
- Mantenuto il filtro per sessione nelle query, evitando di mescolare dati appartenenti a notti differenti.
- Ridotto l'intervallo di aggiornamento automatico della dashboard da 5 a 1 secondo.

### Verifiche

- Confermata la presenza di una sessione attiva e di campioni `night_position` aggiornati in InfluxDB.
- Eseguita con successo su InfluxDB la nuova query di selezione automatica dell'ultima sessione.
- Validata la sintassi JSON della dashboard Grafana.

## 20 luglio 2026 — Area Medico consultiva diurna e notturna

### Modifiche

- Riorganizzata la scheda del paziente in due aree graficamente distinte: `Monitoraggio diurno` e `Monitoraggio notturno`.
- Mantenuto sempre visibile il pannello diurno live, mostrando uno stato esplicito quando non sono presenti dati in tempo reale.
- Rinominato e mantenuto sempre disponibile lo `Storico diurno`, con l'intera finestra temporale rappresentata dal grafico.
- Aggiunto al Medico il pannello notturno live in sola lettura, sempre visibile anche quando la modalità notte non è attiva.
- Collegato il flusso WebSocket notturno anche al paziente selezionato dal Medico.
- Aggiunto lo storico notturno del paziente con finestre di 7, 30 e 90 giorni oppure tutte le sessioni disponibili.
- Mostrati per ogni sessione notturna data, ora, durata, stato, posizione prevalente e numero di cambi posizione.
- Rimossi dall'area Medico tutti i campi e le azioni per caricare, modificare, salvare o ripristinare soglie e parametri di monitoraggio.
- Evitata l'attivazione automatica del tema scuro nell'account Medico quando un paziente avvia la modalità notte.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente.
- Verificato che il Medico utilizzi gli endpoint notturni esclusivamente in lettura e che i comandi di avvio/arresto restino disponibili solo al Paziente.

## 20 luglio 2026 — Grafici storici per assi e riepilogo dispositivo

### Modifiche

- Sostituito l'elenco testuale dello storico notturno con un grafico temporale coerente con la presentazione dello storico diurno.
- Il grafico notturno mostra, per tutte le sessioni comprese nella finestra selezionata, la percentuale di tempo trascorsa in posizione supina, prona, in decubito destro e in decubito sinistro.
- Mantenuti i filtri notturni per 7, 30 e 90 giorni oppure per tutte le sessioni disponibili.
- Suddiviso lo storico diurno in due grafici distinti: `Deviazione pitch` e `Deviazione roll`, utilizzando i corrispondenti campi persistiti in InfluxDB.
- Conservata sui due grafici diurni la distinzione visiva tra campioni corretti e scorretti.
- Spostate le informazioni su tipo di dispositivo e batteria subito sotto il nome del Paziente.
- Applicato il nuovo riepilogo sia all'area personale del Paziente sia alla scheda aperta dal Medico.
- La batteria viene mostrata solo quando lo stato ricevuto appartiene allo stesso dispositivo visualizzato, evitando associazioni errate tra pazienti.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente con i nuovi grafici.

## 20 luglio 2026 — Istogramma notturno e ricerca sessioni

### Modifiche

- Sostituito il grafico lineare dello storico notturno con un istogramma a quattro colonne.
- L'istogramma mostra esclusivamente le percentuali di tempo in posizione supina, prona, in decubito destro e in decubito sinistro.
- Le percentuali aggregate considerano tutte le sessioni comprese nella finestra temporale selezionata.
- Aggiunto un menu a tendina contenente tutte le sessioni notturne disponibili del paziente.
- Aggiunto un campo di ricerca nel menu per filtrare rapidamente le sessioni utilizzando data numerica, data estesa oppure orario.
- Selezionando una singola sessione, l'istogramma viene ricalcolato esclusivamente sui dati di quella notte.
- Aggiunta l'opzione per tornare alla visualizzazione aggregata di tutte le sessioni del periodo.
- Per ogni voce del menu vengono mostrati data, ora, durata e stato della sessione.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente con istogramma, menu a tendina e ricerca per data.

## 20 luglio 2026 — Grafico a torta notturno per il Paziente

### Modifiche

- Aggiunto nella pagina Paziente un grafico a torta all'interno della modalità notte attiva.
- Il grafico mostra la distribuzione percentuale tra posizione supina, prona, decubito destro e decubito sinistro.
- Colori e diciture sono coerenti con i contatori notturni e con le altre visualizzazioni dell'app.
- Le percentuali si aggiornano in tempo reale utilizzando gli stessi contatori fluidi mostrati nel pannello.
- Prima della ricezione dei primi dati classificati viene mostrato uno stato informativo al posto di un grafico vuoto.
- Il grafico resta esclusivo della pagina Paziente e non viene duplicato nel pannello live consultivo del Medico.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente con il nuovo grafico a torta.

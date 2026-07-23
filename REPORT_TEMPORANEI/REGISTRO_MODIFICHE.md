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

## 20 luglio 2026 — Rimozione calibrazione Paziente e centraggio torta

### Modifiche

- Rimosso dalla pagina Paziente il pulsante `Calibra postura di riferimento`.
- Rimossi dal codice mobile anche lo stato e la funzione di calibrazione non più utilizzati.
- Ridotta la larghezza del grafico a torta in base allo spazio interno effettivo della card.
- Eliminato lo spostamento laterale del grafico e aggiunto un centraggio esplicito.
- Evitato il taglio del bordo sinistro del grafico sui display più stretti.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente dopo la correzione grafica.

## 20 luglio 2026 — Suddivisione Paziente diurna/notturna

### Modifiche

- Riorganizzata la pagina Paziente in due sezioni graficamente distinte: `Monitoraggio diurno` e `Monitoraggio notturno`, coerenti con la struttura già usata dal Medico.
- Mantenuta visibile la sezione diurna anche durante una sessione notturna, mostrando l'eventuale assenza di dati live senza nascondere lo storico.
- Limitato lo storico diurno del Paziente alle percentuali di postura corretta e scorretta.
- Mantenute le visualizzazioni dettagliate Pitch e Roll esclusivamente nella consultazione del Medico.
- Rimossi i punti dalle curve dei grafici storici Pitch e Roll.
- Ripristinata l'impostazione orizzontale precedente del grafico a torta e ridotto soltanto il diametro della circonferenza tramite l'altezza del grafico.
- Corretta la descrizione `Il tuo monitoraggio posturale` nella testata Paziente.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente con la nuova struttura Paziente.

## 20 luglio 2026 — Grafici Pitch e Roll live e storico Paziente

### Modifiche

- Separato il precedente grafico unico in tempo reale in due grafici distinti: `Pitch in tempo reale` e `Roll in tempo reale`.
- Applicata la nuova visualizzazione sia alla pagina personale del Paziente sia alla scheda del Paziente consultata dal Medico.
- Collegati i grafici ai valori specifici `pitch_deviation_deg` e `roll_deviation_deg` calcolati dal backend rispetto ai rispettivi riferimenti.
- Mantenute le curve senza punti sui singoli campioni per una lettura più pulita.
- Aggiunti allo storico diurno del Paziente i grafici `Deviazione pitch` e `Deviazione roll`, già disponibili nella vista del Medico.
- Conservato nel lato Paziente anche il riepilogo percentuale delle posture corrette e scorrette.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente con i nuovi grafici.

## 20 luglio 2026 — Riferimenti di calibrazione nei grafici live

### Modifiche

- Aggiunti nella sezione diurna due riquadri riepilogativi per il riferimento calibrato di pitch e per quello di roll.
- Applicati i riquadri sia alla pagina Paziente sia alla scheda del Paziente consultata dal Medico.
- Modificati i grafici in tempo reale per mostrare l'angolo effettivamente rilevato, coerentemente con i grafici Grafana.
- Aggiunta in ciascun grafico una linea orizzontale corrispondente al riferimento di calibrazione corrente.
- I valori e le linee usano `reference_pitch_deg` e `reference_roll_deg` ricevuti dal backend nei campioni WebSocket.
- Una calibrazione eseguita da Grafana viene quindi riflessa nell'app a partire dal campione posturale successivo ricevuto dalla maglia.
- Distinti graficamente il valore rilevato e la calibrazione mediante colori e legenda.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente con riquadri e riferimenti di calibrazione.

## 20 luglio 2026 — Scala live controllata e associazione rimossa

### Modifiche

- Trasformate in tratteggiate le linee orizzontali che rappresentano i riferimenti di calibrazione nei grafici Pitch e Roll.
- Impostato per entrambi i grafici un intervallo verticale minimo compreso tra `-30°` e `+30°`.
- La scala si amplia automaticamente quando un valore rilevato o un riferimento calibrato supera uno dei due limiti.
- Applicato il comportamento sia alla pagina Paziente sia alla scheda consultata dal Medico.
- Rimossa dall'app la funzionalità di associazione di un nuovo Paziente tramite codice fiscale.
- Rimossi anche stato, chiamata API, tendina, pulsante e stili non più utilizzati dal relativo flusso.
- Aggiornato lo stato vuoto della lista Medico per indicare che le associazioni vengono gestite esternamente all'app.

### Verifiche

- Controllo TypeScript completato senza errori nel container Expo.
- Bundle Android Expo generato correttamente con le nuove impostazioni dei grafici.

## 21 luglio 2026 — Dashboard notturna limitata alla sessione live

### Modifiche

- Sostituito nella dashboard Grafana notturna il pannello `Stato mod. notte` con un riquadro `Monitoraggio`.
- Il nuovo riquadro mostra `ON` su fondo verde durante una sessione attiva e `OFF` su fondo rosso quando il monitoraggio è fermo.
- Introdotta in InfluxDB la measurement `night_session_state`, aggiornata dal backend con `active=1` all'avvio e `active=0` alla conclusione della sessione.
- Aggiunta all'avvio del backend la riconciliazione delle sessioni che risultano ancora attive in SQLite.
- Vincolate la posizione corrente e le query dei quattro grafici notturni alla sola sessione effettivamente attiva.
- Alla disattivazione i grafici live non mostrano più i dati dell'ultima sessione conclusa; questi rimangono disponibili esclusivamente nello storico.
- Aggiunto sotto i quattro grafici un istogramma live con le percentuali di posizione supina, prona, decubito destro e decubito sinistro.
- Le quattro percentuali vengono calcolate solo sui campioni della sessione corrente e tornano a zero al termine della modalità notte.
- Mantenuti nell'istogramma gli stessi colori utilizzati per le quattro posizioni negli altri pannelli.
- Aggiunto un test backend per verificare la pubblicazione dello stato ON/OFF con lo stesso identificativo di sessione.

### Verifiche

- Validazione sintattica JSON della dashboard completata correttamente.
- Test backend della modalità notturna completati senza errori.
- Verifica delle query e del provisioning Grafana completata sullo stack Docker.

## 21 luglio 2026 — Controlli dashboard notturna

### Modifiche

- Ridotto il riquadro `Monitoraggio` alle stesse proporzioni del corrispondente indicatore presente nella dashboard diurna.
- Ripristinato accanto all'indicatore il pulsante per attivare o disattivare la modalità notte dalla dashboard Grafana.
- Mantenuto lo stato esclusivamente nel riquadro `Monitoraggio`, evitando di duplicare la precedente dicitura `Stato mod. notte` nel pannello del pulsante.
- Limitate le finestre di ricerca delle query live Grafana per evitare che il refresh ogni secondo riesamini l'intero contenuto di InfluxDB e venga annullato prima di restituire i campioni.
- Verificato che app e Grafana operino sulla stessa sessione: l'avvio da una delle due interfacce è immediatamente valido anche per l'altra, che può successivamente arrestarla.
- Verificato il comportamento indipendente dalla sorgente: la maglia fisica continua a inviare i propri campioni MQTT senza ricevere comandi da simulatore; solo le maglie simulate cambiano scenario automaticamente.
- Alla riconnessione MQTT il backend ripristina lo scenario notturno esclusivamente per le maglie simulate con una sessione ancora attiva, evitando uno stato ON accompagnato da campioni diurni dopo un riavvio.
- Sostituiti nelle query live i `join` Flux tra stato e campioni con un filtro diretto sul `session_id` attivo; i campioni erano presenti e classificati in InfluxDB, ma il collegamento tra tabelle poteva restituire pannelli vuoti o richieste annullate.

## 21 luglio 2026 — Storico diurno sincronizzato con la giornata selezionata

### Modifiche

- Allineati `Dev. Media Pitch`, `Dev. Media Roll`, deviazioni massime, numero di alert e grafici Pitch/Roll all'intervallo della giornata scelta nel selettore.
- Il cambio della giornata aggiorna anche l'intervallo temporale globale di Grafana, così `v.windowPeriod`, assi e aggregazioni vengono ricalcolati sulla selezione corrente.
- Rinominato il controllo da `Alert per giornata` a `Storico per giornata`, perché ora governa l'intera dashboard e non soltanto la tabella degli alert.
- Corretto l'intervallo globale Grafana usando timestamp Unix in millisecondi: le date ISO venivano interpretate come piccoli valori numerici e spostavano erroneamente gli assi dei grafici nel 1970.
- Limitato il contatore superiore agli eventi posturali attivi, escludendo alert tecnici relativi a batteria, connettività e qualità del dato.
- Rimossa la risincronizzazione automatica dell'URL al caricamento perché la normalizzazione dei timestamp eseguita da Grafana poteva provocare un ciclo continuo di ricaricamento; l'intervallo viene aggiornato soltanto alla selezione esplicita della giornata.

## 21 luglio 2026 — Vere sessioni diurne ed episodi posturali

### Modifiche

- Aggiunto `session_id` a ogni campione diurno persistito in InfluxDB; la sessione nasce al primo campione e viene rinnovata alla ripresa dopo un'interruzione del flusso.
- Sostituito il selettore per giornata con un selettore di singole sessioni, etichettate con data, ora di inizio e ora di fine rilevate dai campioni.
- Vincolati statistiche, grafici e tabella alert sia all'intervallo sia al `session_id` selezionato.
- Aggiunto il campo `episode_started` agli alert: vale vero soltanto al passaggio da postura corretta al primo stato di allerta.
- Il contatore `Eventi posturali` conta ora gli episodi distinti e non i passaggi interni tra deviazione prolungata e marcata.
- Aggiornata l'etichetta del filtro delle sessioni in `Cerca per data o ora`, con un esempio coerente nel campo di ricerca.
- Rimosse le emoji dalla navigazione e dai pannelli Grafana.
- Uniformati i collegamenti principali in `DIURNO`, `STORICO D`, `NOTTURNO` e `STORICO N`.
- Rimossa l'emoji anche dal pulsante di attivazione e disattivazione della modalità notte.
- Colorati uniformemente i collegamenti Grafana: `HOME` bianco, `DIURNO` e `STORICO D` gialli, `NOTTURNO` e `STORICO N` blu.
- Modificato il blu della navigazione notturna in una tonalità più scura (`#234f8f`), distinta dal blu dei pulsanti operativi delle interfacce.

## 21 luglio 2026 — Rilevazione delle maglie fisiche da MQTT

### Modifiche

- Separata la rilevazione della presenza fisica della maglia dall'elaborazione dei dati posturali.
- Il backend rileva ora una smart shirt non appena riceve un qualsiasi topic conforme a `unisadiem/smartshirt/<device>/<packet-type>`.
- Una maglia che trasmette inizialmente soltanto `ECG` o `STRAINGAUGES_MIXED` compare quindi tra le maglie rilevate nella Home medica.
- I payload ECG e strain gauge continuano a non essere elaborati, archiviati o utilizzati per il monitoraggio posturale.
- Limitato a un aggiornamento ogni cinque secondi il salvataggio della presenza, per evitare scritture eccessive causate dai flussi ad alta frequenza.
- Aggiunto un test automatico che verifica la rilevazione di `tshirt002` da un pacchetto non posturale senza decodificarne il payload.
- Corretta la rimozione delle maglie fisiche: la rimozione ora libera la proprietà del medico e rende nuovamente acquisibile la maglia da un altro account, conservando telemetria e storico delle assegnazioni.
- Mantenuta l'archiviazione definitiva per le sole maglie simulate create dal portale.

## 21 luglio 2026 — Dialogo maglie e logout Grafana

### Modifiche

- Ridotti gli spazi verticali nel dialogo di aggiunta della maglia, in particolare tra i campi nome, i messaggi di errore vuoti e i pulsanti di conferma.
- Compattati titoli, descrizioni e separatore tra acquisizione fisica e creazione simulata.
- Trasformato il cookie del portale medico in cookie di sessione, non più persistente per otto ore dopo la chiusura completa del browser.
- Rafforzato il comando `Esci`: oltre a invalidare la sessione nel database, cancella i cookie del sito e impedisce il riuso della pagina dalla cache.
- Allineato il pulsante `Annulla` nell'angolo inferiore destro del popup di aggiunta della maglia.
- Allineato allo stesso modo il pulsante `Annulla` del popup di aggiunta del paziente.

## 21 luglio 2026 — Riorganizzazione monitoraggio mobile diurno e notturno

### Modifiche

- Reso più contenuto il focus dei campi di accesso e registrazione: bordo verde e fondo evidenziato senza elevazione che fuoriesce dal riquadro.
- Separate le sezioni `DIURNO` e `NOTTURNO` in due schede dedicate, sia per il paziente sia per il medico che consulta un paziente.
- Rimosso il precedente riquadro riepilogativo della deviazione corrente con avatar e colore variabile.
- Introdotte due righe di metriche live: Pitch, deviazione Pitch e relativo tempo; Roll, deviazione Roll e relativo tempo.
- Applicati ai riquadri di deviazione i valori moderate/marked ricevuti dal backend, con fallback 10°/20°; applicate ai tempi le fasce Grafana verde sotto 5 s, gialla 5–15 s e rossa da 15 s.
- Riordinati i riferimenti di calibrazione nella riga richiesta e mantenuti separati i grafici live Pitch e Roll.
- Impostata per gli storici diurni una scala minima fissa da −30° a +30°, che si espande automaticamente in presenza di valori esterni.
- Aumentati fino a cinque i riferimenti temporali sull'asse X e aggiunti margini interni per evitare il taglio delle etichette laterali.
- Racchiuso ogni input di autenticazione in un contenitore arrotondato con ritaglio, eliminando la superficie rettangolare del focus visibile su Android.
- Abilitato il ridimensionamento della schermata di autenticazione su Android e l'adattamento automatico degli inset della tastiera, mantenendo scorrevole il form durante la compilazione.
- Spostate le etichette temporali dello storico all'interno dell'8%–92% della larghezza utile, così prima e ultima indicazione non vengono tagliate dai bordi.
- Corretto l'ordine delle metriche diurne: `PITCH` e `ROLL` sono ora i primi riquadri a sinistra, seguiti rispettivamente da deviazione e tempo di deviazione.

### Verifica integrità storico diurno

- Verificata la catena InfluxDB → endpoint storico → grafici mobile sui dati effettivamente presenti.
- Confermato che il grafico Pitch usa esclusivamente `pitch_deviation_deg` e il grafico Roll usa esclusivamente `roll_deviation_deg`.
- Confrontati oltre 121.000 campioni grezzi: la deviazione coincide con `angolo − riferimento` con residuo massimo di 0,01°, compatibile con l'arrotondamento a due decimali.
- Verificati ordinamento cronologico, intervalli selezionati, aggregazione temporale e separazione per paziente.
- Eseguiti con esito positivo 13 test del contratto storico e il controllo TypeScript dell'app.
- Uniformato il focus degli intervalli dello storico diurno al verde chiaro della scheda `DIURNO` e del riquadro paziente.
- Sostituito nel riquadro del paziente selezionato il codice interno con il codice fiscale, esposto dal backend soltanto nei dati autorizzati dell'utente.

## 21 luglio 2026 — Isolamento della telemetria in tempo reale per paziente

### Correzione

- Corretto il filtro mobile che, nella vista paziente, utilizzava erroneamente l'ultimo campione globale ricevuto dal WebSocket.
- La vista paziente accetta ora esclusivamente campioni il cui `patient_id` coincide con il proprio codice paziente.
- Autenticato il WebSocket tramite la sessione dell'app e vincolata lato backend ogni connessione a un solo paziente autorizzato.
- Il medico riceve esclusivamente la telemetria del paziente selezionato; senza selezione non viene aperta alcuna connessione live.
- Impedita anche lato server la consegna di telemetria appartenente ad altri pazienti, evitando che la protezione dipenda soltanto dal rendering dell'app.
- Aggiunti test automatici di instradamento che verificano che un campione di Andrea non venga consegnato alla connessione di Simona e che messaggi privi di paziente non vengano diffusi.

## 21 luglio 2026 — Accesso richiesto a ogni avvio dell'app

### Modifiche

- Rimossa la riapertura automatica dell'ultima sessione utente salvata in `SecureStore`.
- La sessione di autenticazione resta valida soltanto durante l'esecuzione corrente dell'app.
- A ogni nuovo avvio o scansione del QR viene cancellata un'eventuale sessione precedente e mostrata sempre l'interfaccia login/registrazione.
- Le preferenze non legate all'identità, come il tema, continuano a essere conservate separatamente.
- Corretto l'ordine visivo dei valori di calibrazione: `RIFERIMENTO PITCH` a sinistra e `RIFERIMENTO ROLL` a destra.

## 22 luglio 2026 — Storico diurno mobile per sessione

### Modifiche

- Uniformato lo storico diurno del paziente e del medico aggiungendo l'elenco delle sessioni diurne disponibili.
- Aggiunta la ricerca delle sessioni per data o ora e la possibilità di tornare all'intera finestra temporale selezionata.
- Quando viene scelta una sessione, percentuali e grafici Pitch/Roll vengono calcolati esclusivamente tra l'inizio e la fine della sessione.
- Mantenute nel solo profilo Paziente le percentuali `Postura corretta` e `Postura scorretta`.
- Le percentuali provengono ora dal medesimo risultato storico del backend: un campione è corretto solo quando sia Pitch sia Roll restano sotto le rispettive soglie moderate; una deviazione moderata o marcata su almeno un asse viene conteggiata come scorretta.
- Rimossa dall'area Paziente la nota grigia `Soglie dimostrative, non validate per uso clinico` visualizzata dopo il monitoraggio.
- Negli storici diurno e notturno, la selezione di una singola sessione disabilita i pulsanti delle finestre temporali e ne rimuove l'evidenziazione; i pulsanti tornano disponibili scegliendo la vista complessiva.
- Rimossi dai grafici live Pitch e Roll i sottotitoli grigi relativi al valore rilevato, alla calibrazione e al numero di campioni.
- Rimossa la parola `Paziente` dalla descrizione sotto il saluto; per il profilo paziente rimane soltanto `Il tuo monitoraggio posturale`.

## 22 luglio 2026 — Visualizzazione controllata delle credenziali

### Modifiche

- Aggiunta un'icona vettoriale a forma di occhio ai campi password dell'app, senza utilizzare emoji.
- Il comando permette di mostrare e nascondere il contenuto e dispone di un'etichetta accessibile coerente con lo stato.
- Reso nascosto per impostazione predefinita anche il codice medico nell'app e aggiunto lo stesso comando di visualizzazione.
- Aggiunto il comando mostra/nascondi al codice medico nella schermata di registrazione del portale Grafana, riutilizzando l'icona SVG già adottata per le password.
- Corretto l'asse temporale dei grafici storici diurni: le finestre da 1, 6, 24 ore e 7 giorni mostrano sempre l'intervallo completo richiesto, anche quando la prima parte non contiene campioni.
- I dati vengono posizionati in base al timestamp reale, lasciando vuoto lo spazio precedente al primo campione e successivo all'ultimo; selezionando una sessione, l'asse usa invece l'inizio e la fine effettivi della sessione.

## 22 luglio 2026 — Riorganizzazione del monitoraggio notturno mobile

### Modifiche

- Rimossa dal pannello Paziente inattivo la nota grigia relativa all'attivazione automatica del tema e alla vista notturna.
- Durante una sessione attiva, il badge `Live` rimane accanto al titolo e il pulsante rosso di arresto è stato spostato immediatamente sotto l'intestazione.
- Il medico visualizza posizione, tempi, distribuzione percentuale e durata della sessione, ma non dispone di comandi per avviare o terminare la modalità notte.
- Reso disponibile il grafico a torta live anche nella vista Medico; la torta è stata ridimensionata e centrata e la legenda è stata separata per evitare tagli dei nomi delle posizioni.
- Sostituita la riga grigia con maglia e durata con un riquadro dedicato `DURATA TOTALE`.
- Separata la preferenza manuale del tema dall'attivazione automatica notturna: la preferenza viene salvata per singolo utente, mentre la modalità notte applica soltanto un override temporaneo.
- Al logout l'override notturno viene rimosso senza interrompere la sessione sul backend; al successivo accesso viene caricata la preferenza del nuovo account e l'eventuale modalità notte attiva viene poi sincronizzata.
- Aggiunto nella sezione `NOTTURNO` del Paziente un riquadro `Storico notturno`, con lo stesso sfondo del riquadro esplicativo del monitoraggio.
- Il riquadro contiene un solo istogramma verticale con le percentuali persistenti complessive di supino, prono, decubito destro e decubito sinistro.
- Introdotto un endpoint aggregato che calcola i totali su tutte le sessioni notturne concluse, senza il limite dell'elenco paginato e senza includere la sessione live ancora attiva.
- Aumentato lo spazio sopra le barre degli istogrammi notturni e riallineata la guida del 100%, evitando che la linea orizzontale attraversi le etichette percentuali.
- Corretto l'indicatore `Live` nella lista pazienti del medico: ora considera sia la telemetria diurna corrente sia una sessione notturna attiva, che continua a risultare live anche dopo il logout del paziente.
- La lista dei pazienti viene aggiornata silenziosamente ogni cinque secondi, così l'avvio o la conclusione della modalità notte viene riflesso senza dover riaprire l'app.
- Ritagliato esclusivamente il margine trasparente superiore del logo usato nella schermata di accesso e adeguata l'altezza del componente, eliminando lo spazio vuoto che spostava inutilmente il form verso il basso.

## 22 luglio 2026 — Stato del monitoraggio nella scheda dispositivo

### Modifiche

- Aggiunto accanto alla batteria il terzo indicatore `Monitoraggio`, visibile sia al paziente sia al medico che consulta un paziente.
- Lo stato segue la stessa regola della dashboard Grafana: è `ON` in verde quando è presente telemetria posturale diurna ricevuta negli ultimi 10 secondi, altrimenti è `OFF` in rosso.
- Durante una sessione notturna lo stato del monitoraggio diurno rimane `OFF`, coerentemente con Grafana.
- Resa più compatta la scheda riepilogativa per ospitare dispositivo, batteria e monitoraggio senza sovrapposizioni su schermi mobili.

## 22 luglio 2026 — Eliminazione dell'account

### Modifiche

- Aggiunta nelle impostazioni una sezione dedicata all'eliminazione dell'account, distinta graficamente come azione irreversibile.
- Prima dell'operazione viene mostrata una conferma esplicita che informa l'utente della perdita dell'accesso e della conservazione del profilo di monitoraggio gestito dal medico.
- L'eliminazione riguarda esclusivamente l'account digitale: revoca le sessioni, rimuove i token, l'avatar e rende definitivamente inutilizzabili le credenziali.
- Nome, cognome e codice fiscale restano nel profilo di monitoraggio, coerentemente con la possibilità per il medico di gestire da Grafana anche pazienti privi di account sull'app.
- Associazione medico-paziente, maglia assegnata, eventuale monitoraggio attivo, misurazioni, sessioni, calibrazioni e configurazioni restano invariati.
- Aggiunta nelle impostazioni la sezione `Sicurezza`, dalla quale è possibile aprire la schermata di cambio password già disponibile nel profilo.
- Rimossa dal riquadro `Elimina account` la nota descrittiva grigia; le conseguenze dell'operazione restano illustrate nella finestra di conferma.
- Rinominata da `Monitoraggio` a `Stato` l'etichetta dell'indicatore ON/OFF affiancato alla batteria.
- Abbreviata da `Tipo dispositivo` a `Dispositivo` l'etichetta del riepilogo della maglia.
- Uniformato il tema del riquadro `Storico diurno` a quello del riquadro `Monitoraggio diurno`, sia nella vista Paziente sia nella consultazione del paziente da parte del Medico.
- Uniformato il tema degli storici notturni al riquadro `Monitoraggio notturno`, con sfondo azzurro e bordo coordinato nelle viste Paziente e Medico.
- Arricchito lo storico notturno del Medico, sulla base dei pannelli Grafana, con i tempi effettivi in posizione supina, prona, decubito destro e decubito sinistro e con il tempo non classificato.
- I tempi mostrati si aggiornano insieme al selettore: rappresentano la singola sessione scelta oppure il totale delle sessioni comprese nella finestra temporale.

## 22 luglio 2026 — Preparazione APK Android e notifiche push

### Riferimento didattico

- Analizzate integralmente le slide `incontri_applicazione_mobile.pdf`, con particolare attenzione alle pagine 28-37 dedicate a Expo Push Token, Expo Dev Client, APK development, Firebase e credenziali FCM V1.
- Confermato che Expo Go non supporta le notifiche push remote Android con SDK 54: è necessaria una development build installabile.

### Modifiche

- Installato `expo-dev-client` compatibile con Expo SDK 54 e aggiunto un profilo EAS `development` che produce un APK per distribuzione interna.
- Configurato `expo-notifications`, due canali Android separati (`Avvisi posturali` e `Smart t-shirt`) e la registrazione dell'Expo Push Token sul backend dopo l'accesso.
- Aggiunte API autenticate per registrare/rimuovere il token del singolo telefono e inviare una notifica di prova dalle Impostazioni.
- Implementato l'invio server-side tramite Expo Push Service, operativo anche con app in background o chiusa dopo la configurazione FCM.
- Le notifiche automatiche riguardano deviazione pronunciata, deviazione prolungata, batteria bassa, batteria critica e interruzione del flusso dati.
- Gli eventi di ripristino e ritorno alla postura corretta restano nello storico ma non generano notifiche, riducendo notifiche ridondanti.
- La batteria genera una sola notifica al passaggio sotto il 20% e un eventuale secondo avviso al passaggio sotto il 10%, non a ogni campione.
- Aggiunti al `.gitignore` i file Firebase e le chiavi di servizio, che non devono essere versionati.

### Passaggi esterni ancora necessari

- Collegare il progetto a un account Expo/EAS per ottenere il `projectId`.
- Creare l'app Android `it.smartback.monitoring` su Firebase, fornire localmente `google-services.json` e caricare su EAS la chiave Service Account FCM V1.
- Generare l'APK con il profilo development e verificare sul dispositivo fisico la notifica di prova e gli alert reali.
- Collegato il progetto EAS `@3ab/smartback` e configurato l'uso di `GOOGLE_SERVICES_JSON` come variabile-file protetta per rendere disponibile al builder il file Firebase escluso da Git.
- Impostata esplicitamente la sorgente remota della versione dell'app e l'ambiente EAS `development`, eliminando gli avvisi mostrati dalla prima procedura di build.
- Sostituita l'icona launcher con il file `icona_app_smartback.png` fornito, senza modificarne contenuto o proporzioni.
- Rimossa dalle Impostazioni la sezione con il pulsante per la notifica di prova; registrazione del telefono e notifiche automatiche restano attive.
- Aggiornato il testo della deviazione prolungata in `Fai una pausa e raddrizza la schiena.`; la soglia temporale effettiva resta pari a 5 secondi.
- Abilitato l'incremento automatico del `versionCode` anche per gli APK development, così le nuove build possono aggiornare correttamente l'app Android già installata.
- Aggiunta nell'intestazione dell'app una campanella vettoriale, posizionata a sinistra dell'icona profilo, che apre l'archivio delle notifiche SmartBack.
- Le notifiche generate dal backend vengono ora conservate in SQLite per l'account destinatario e mostrate in ordine cronologico con giorno e orario, anche quando l'app era chiusa al momento dell'invio.
- Aggiunto nella parte superiore dell'archivio il comando `Cancella`, protetto da conferma, per eliminare tutte le notifiche dell'account.
- Nella lista pazienti del Medico sostituito l'identificativo tecnico visualizzato sotto l'email con il codice fiscale del paziente.
- Aggiunto all'archivio notifiche il comando `Aggiorna` e il gesto pull-to-refresh, entrambi collegati a un nuovo caricamento dal backend.
- Verificata la catena remota Expo/FCM con una notifica diagnostica: ticket e ricevuta risultano entrambi `ok`; l'eventuale mancata visualizzazione nella tendina dipende quindi dai permessi o dai canali Android del dispositivo.
- Ripetuta la diagnosi separatamente sui due token associati all'account: entrambi hanno ottenuto ticket Expo e ricevuta FCM `ok`, confermando che il blocco di visualizzazione è locale al sistema Android.
- Aggiunta nelle Impostazioni la sezione `Notifiche del telefono`, che mostra lo stato effettivo del permesso Android e apre direttamente le impostazioni native di SmartBack per abilitare notifiche, banner e canali.
- Sostituiti i canali Android precedenti con nuovi identificativi interni, evitando che impostazioni silenziate conservate dal sistema operativo continuino a bloccare la visualizzazione.
- Impostata priorità massima lato app e priorità alta con durata di un'ora lato Expo/FCM; abilitati esplicitamente suono, vibrazione e visibilità nella schermata di blocco.
- Individuata nei log la causa della divergenza fra archivio interno e tendina Android: gli alert automatici venivano salvati correttamente, ma alcuni invii a Expo fallivano per errori DNS temporanei (`Name or service not known`).
- Aggiunti quattro tentativi automatici con attesa esponenziale per gli errori temporanei di rete/DNS e un log esplicito del numero di messaggi accettati da Expo.
- Verificato il nuovo percorso usando lo stesso payload di una deviazione pronunciata automatica: Expo ha accettato l'invio per tutti i token registrati.
- Verificato con ESP connesso che gli alert reali venivano generati, ma gli invii concorrenti saturavano la risoluzione DNS del container e fallivano anche dopo i retry.
- Serializzati gli invii verso Expo e introdotto un intervallo minimo di 60 secondi per account e tipo di notifica, evitando raffiche duplicate e richieste DNS concorrenti.
- L'archivio della campanella viene ora aggiornato solo dopo l'accettazione dell'invio da parte di Expo: non mostra più come ricevute notifiche che non hanno superato il passaggio di consegna.
- Verificato che la rete corrente consente il traffico locale ESP/MQTT ma presenta risoluzione DNS Internet instabile o assente dal container; questo spiega perché la telemetria locale può funzionare mentre Expo/FCM fallisce.
- Separato nuovamente, in modo controllato, l'archivio interno dalla consegna remota: ogni nuovo alert viene conservato nella campanella anche senza Internet, con un massimo di un evento al minuto per tipo, mentre la notifica Android viene inviata quando Expo è raggiungibile.
- Estesa la consegna remota a otto tentativi con intervalli progressivi fino a 30 secondi, coprendo interruzioni Internet temporanee sensibilmente più lunghe.
- Verificata nuovamente la raggiungibilità di Expo sia dal Mac sia dal container (`HTTP 200`) e accettato un payload reale di deviazione pronunciata su tutti i token registrati.
- Lo screenshot del telefono ha confermato la consegna differita FCM: notifiche generate tra le 17:32 e le 17:35 sono comparse insieme alle 17:41 dopo il passaggio da OpenWrt a una rete con accesso Internet.
- Confermato il requisito multi-dispositivo: ogni account può registrare contemporaneamente più Expo Push Token, uno per ciascun telefono o tablet. Eventuali dispositivi rimossi durante la diagnosi vengono registrati nuovamente al successivo login.

## 23 luglio 2026 — Riepilogo dispositivo e monitoraggio contestuale

### Modifiche

- Sostituita nell'app la derivazione del dispositivo dall'ultimo campione WebSocket con un endpoint autenticato e specifico per il paziente selezionato.
- Il riquadro `Dispositivo` mostra ora esclusivamente tipologia e nome assegnato nell'inventario, senza esporre l'identificativo tecnico.
- Il nome viene mostrato solo quando la maglia è ancora assegnata e ha trasmesso recentemente; in caso di disconnessione o deallocazione da Grafana compaiono `OFF`, testo rosso e icona rossa.
- Ridotto a cinque secondi l'intervallo di aggiornamento del riepilogo, così disconnessioni e deallocazioni vengono riflesse rapidamente sia lato Paziente sia lato Medico.
- Reso il riquadro `Stato` dipendente dalla scheda selezionata: in `DIURNO` segue la telemetria posturale recente, in `NOTTURNO` segue l'attivazione della sessione notturna.
- Semplificato il pannello blu notturno rimuovendo titolo, nota ed elemento lunare; il comando inattivo è ora `ATTIVA MONITORAGGIO` con il blu della scheda notturna.
- Rinominato il comando di arresto in `TERMINA MONITORAGGIO`, mantenendo il badge Live e i dati della sessione quando attiva.
- Rimosso successivamente il badge `Live` dal pannello del monitoraggio notturno.
- Semplificato ulteriormente `Dispositivo`: quando connesso mostra soltanto il nome assegnato alla maglia, senza tipologia né identificativo tecnico.

### Verifiche

- Compilazione TypeScript completata senza errori.
- Eseguiti 93 test backend con esito positivo, incluso il nuovo caso su nome dispositivo, connessione e deallocazione.

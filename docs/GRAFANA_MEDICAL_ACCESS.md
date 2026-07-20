# Accesso medico a Grafana

Grafana e destinato esclusivamente al medico. La dashboard principale mostra
soltanto inclinazioni pitch/roll, durata delle deviazioni, batteria e alert del
paziente selezionato.

## Accesso

Aprire:

```text
http://localhost:3000
```

Il medico usa le stesse credenziali SmartBack. Non serve creare un secondo
account manuale in Grafana.

Nell'ambiente locale e disponibile anche l'amministratore tecnico:

```text
utente: admin
password: smartback-dev-password
```

Il campo accetta quindi un indirizzo email medico oppure l'identificativo
`admin`. La password amministrativa deriva da `GRAFANA_ADMIN_PASSWORD` e deve
essere sostituita prima di condividere o distribuire l'ambiente.

Il percorso di autorizzazione e:

1. il medico effettua il login SmartBack e accede alla Home medica;
2. il backend verifica credenziali, `role=doctor` e
   `professional_verified=true`;
3. il gateway rifiuta richieste prive di una sessione medica valida;
4. il gateway comunica a Grafana l'identita verificata;
5. Grafana crea, quando necessario, un profilo con ruolo `Viewer`.

La Home mostra solo i pazienti associati al medico autenticato. Da qui il
medico apre il monitoraggio live o lo storico del paziente e gestisce
l'assegnazione delle magliette disponibili. Il selettore globale del paziente
nelle dashboard è nascosto: il paziente viene scelto dalla Home.

Le magliette vengono aggiunte automaticamente all'inventario quando il backend
riceve per la prima volta un loro messaggio. Liberare una maglia chiude
l'assegnazione attiva senza cancellarne lo storico.

L'interfaccia medica non espone la distinzione fra sorgenti fisiche e simulate:
il medico gestisce soltanto magliette, disponibilità e assegnazioni. Nel
prototipo `Maglia 2` utilizza la telemetria reale; le unità aggiunte manualmente
sono alimentate dal simulatore come dettaglio tecnico trasparente.

Un paziente, un medico non verificato o un visitatore anonimo non possono
aprire la dashboard.

## Protezioni attive

- accesso anonimo e registrazione autonoma disabilitati;
- dashboard in sola lettura per il medico;
- ruolo Grafana predefinito `Viewer`;
- sezione Explore disabilitata;
- porta diretta Grafana limitata a `127.0.0.1:3001` per manutenzione locale;
- porta medica `3000` esposta soltanto attraverso il gateway;
- logout Grafana collegato alla chiusura della sessione SmartBack.

## Accesso dalla rete locale

Per aprire la dashboard da un altro computer o tablet, sostituire l'indirizzo
in `.env` con l'IP corrente del computer che esegue Docker:

```env
GRAFANA_PUBLIC_URL=http://192.168.1.100:3000/grafana/
GRAFANA_SIGNOUT_URL=http://192.168.1.100:3000/grafana-logout
```

Ricreare poi Grafana e il gateway:

```bash
docker compose up -d --force-recreate grafana grafana-gateway
```

La configurazione usa HTTP soltanto per lo sviluppo locale. In un ambiente
distribuito deve essere aggiunto HTTPS e il cookie di sessione deve essere
marcato `Secure`.

## Modello dei permessi

Grafana OSS supporta auth proxy, utenti Viewer e permessi su folder/dashboard.
La granularita RBAC avanzata e i permessi sui datasource richiedono Grafana
Enterprise o Grafana Cloud.

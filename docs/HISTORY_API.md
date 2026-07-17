# Storico persistente SmartBack

InfluxDB e la fonte unica dello storico temporale. Il bucket `posture` usa
retention infinita: i dati non dipendono dallo stato corrente della maglia e
restano disponibili dopo la disconnessione.

Le app non accedono direttamente a InfluxDB. Paziente e medico usano FastAPI,
che applica le regole di autorizzazione:

- il paziente puo leggere soltanto il proprio storico;
- il medico deve indicare un paziente precedentemente associato;
- Grafana resta una vista riservata ai medici.

## Disponibilita

```http
GET /api/v1/posture/history/availability
GET /api/v1/posture/history/availability?patient_id=<user-id>
Authorization: Bearer <token>
```

La risposta indica se esistono rilevazioni e le date del primo e dell'ultimo
campione:

```json
{
  "has_data": true,
  "first_timestamp": "2026-07-14T09:17:56.388000+00:00",
  "last_timestamp": "2026-07-17T09:37:41.558000+00:00",
  "patient_id": "usr_...",
  "patient_code": "patient-demo-001"
}
```

## Consultazione

Il parametro storico gia usato dall'app resta compatibile:

```http
GET /api/v1/posture/history?minutes=60
```

Per intervalli personalizzati si usano timestamp ISO 8601:

```http
GET /api/v1/posture/history?start=2026-07-01T00:00:00Z&end=2026-07-17T23:59:59Z
```

Il medico aggiunge `patient_id` alla query. `limit` controlla il numero massimo
di punti restituiti, fino a 1200. Il backend sceglie automaticamente la finestra
di aggregazione in base alla durata richiesta, così ora, giorno, settimana e
mese mantengono una dimensione adatta ai grafici.

La risposta contiene:

- `items`: pitch, roll, deviazioni, durata e stato posturale;
- `availability`: primo e ultimo dato disponibili nell'intero archivio;
- `range`: intervallo effettivamente interrogato;
- `aggregation_seconds`: risoluzione temporale applicata;
- `summary`: percentuali, medie, massimi, alert e interruzioni;
- `alerts`: eventi verificatisi nell'intervallo;
- `gaps`: periodi senza campioni oltre la soglia operativa.

`deviation_deg`, `posture_status`, `is_incorrect`, `items`, `count` e `minutes`
restano presenti per compatibilita con l'interfaccia mobile corrente.

L'intervallo massimo di una singola richiesta e 366 giorni. Questo non limita
la conservazione: intervalli piu vecchi restano interrogabili selezionando date
di inizio e fine appropriate.

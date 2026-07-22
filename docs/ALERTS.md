# Alert SmartBack

I codici tecnici restano stabili nei messaggi MQTT e nello storico. Grafana
mostra invece etichette brevi, pensate per distinguere immediatamente problema
e risoluzione.

| Nome mostrato | Codice | Significato | Stato |
|---|---|---|---|
| Forte inclinazione | `POSTURE_MARKED_DEVIATION` | Pitch o roll supera la soglia marcata configurata. | Attivo |
| Inclinazione troppo lunga | `POSTURE_PROLONGED_DEVIATION` | Una deviazione moderata continua oltre il tempo di persistenza. | Attivo |
| Postura ristabilita | `POSTURE_OK` | Pitch e roll sono rientrati nelle soglie con isteresi. | Risolto |
| Nessun dato dalla maglia | `DATA_STREAM_STALE` | Non arrivano campioni posturali da almeno `DATA_STALE_SECONDS`. | Attivo |
| Trasmissione ripresa | `DATA_STREAM_RESTORED` | I campioni hanno ripreso ad arrivare dopo un'interruzione. | Risolto |
| Batteria critica (≤10%) | `BATTERY_CRITICAL` | Carica residua pari o inferiore al 10%. | Attivo |
| Batteria bassa (≤20%) | `BATTERY_LOW` | Carica residua tra 11% e 20%. | Attivo |
| Batteria recuperata (>20%) | `BATTERY_RECOVERED` | La carica e tornata sopra il 20%. | Risolto |
| Pacchetti saltati | `ACC_SEQUENCE_GAP` | Node-RED rileva un salto nel numero progressivo dei pacchetti ACC. | Evento tecnico |
| Perdita dichiarata dalla maglia | `DATA_LOSS` | La maglia invia esplicitamente un pacchetto `DATALOSS`. | Evento tecnico |
| Errore non classificato | codice sconosciuto | Evento non ancora associato a una categoria leggibile. | Da verificare |

`Pacchetti saltati` e `Perdita dichiarata dalla maglia` non sono sinonimi: il
primo viene dedotto da Node-RED confrontando le sequenze, mentre il secondo e
una segnalazione prodotta direttamente dal firmware della smart shirt.

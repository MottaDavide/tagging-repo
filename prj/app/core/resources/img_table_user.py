IMG_TABLE_USER = """Analizza le figure e le tabelle di una singola pagina di un documento bancario interno.
Per ogni elemento produci: descrizione e classificazione visiva.
Le regole vincolanti su ruolo, enti organizzativi, no-hallucination e cap di
lunghezza sono nel system prompt: applicale rigorosamente.

=== REGOLE PER LE DESCRIZIONI DI FIGURE ===
- Identifica sempre il tipo di grafico (barre, linee, torta, mappa coropletica, scatter, ecc.).
- **Enti organizzativi verbatim**: se la figura cita strutture/direzioni/legal entity (es. 'Direzione Impact', 'BdT 17C', 'DC AFC', 'ISYBANK S.P.A.', 'Gruppo ISP'), nominale esattamente come appaiono, senza pronomi o generalizzazioni. Mai inventare enti non presenti.
- Prima di qualsiasi numero, nomina esplicitamente tutte le entità geografiche visibili: paesi, macro-regioni (Nord, Sud, Est, Ovest), regioni, province, città.
- Elenca TUTTE le categorie, le serie di dati, le voci di legenda e le etichette degli assi (elementi non numerici): non usare 'ecc.', '...', 'tra cui' o altre formule abbreviative; cita ogni voce esplicitamente.
- Per mappe geografiche descrivi le aree evidenziate, i confini tracciati e le zone colorate indicando esplicitamente i nomi geografici corrispondenti.
- Spiega il messaggio del grafico e il fenomeno rappresentato, non solo i dati grezzi.
- Cap di lunghezza: ≤200 parole per figura, in italiano. Preferisci 3-5 frasi brevi.

=== REGOLE PER LE DESCRIZIONI DI TABELLE ===
- Inizia con le intestazioni di riga e colonna (elementi non numerici) prima di citare valori.
- Elenca TUTTI i campi/intestazioni presenti, senza fermarti ai primi: non usare 'ecc.', '...', 'tra cui' o formule abbreviative.
- **Enti organizzativi verbatim**: se una colonna o una cella contiene nomi di enti, direzioni, legal entity, riportali esattamente come compaiono. Mai sostituirli con pronomi o generalizzazioni ('la struttura', 'la divisione'). Mai inventare enti non presenti.
- **Formato entity-keyed (preferito)**: se UNA colonna identifica enti organizzativi e le altre colonne sono KPI/percentuali/esiti, produci UNA FRASE PER RIGA con schema '<NomeEnteVerbatim>: <KPI/valori>, <interpretazione qualitativa>.' Questo formato è il più utile a valle del sistema di tagging — privilegialo quando applicabile.
- Nomina esplicitamente eventuali aree geografiche presenti nelle intestazioni o nelle celle.
- Indica l'unità di misura o la tipologia dei dati se desumibile.
- **No hallucination**: nessun ente, valore o percentuale al di fuori di quanto presente nelle righe della tabella sorgente. In caso di incertezza, ometti.
- Cap di lunghezza: ≤200 parole per tabella, in italiano.

=== REGOLE PER LA CLASSIFICAZIONE DI FIGURE (remove_as_layout) ===
- Imposta remove_as_layout=true SOLO per elementi ricorrenti di layout/pagina: logo, header, footer, marchio ripetuto, icona decorativa, elementi grafici istituzionali ricorrenti.
- Grafici, chart, KPI, dashboard, diagrammi, schemi, heatmap, immagini informative e visualizzazioni dati DEVONO avere remove_as_layout=false, anche se appaiono su più pagine.
- Il campo occurrence_count indica su quante pagine compare la stessa figura: usalo solo come indizio, non come regola assoluta.

=== REGOLE PER contains_chart e chart_type ===
- Se la descrizione menziona esplicitamente un tipo di grafico, imposta contains_chart=true obbligatoriamente.
- Se un elemento contiene numeri, assi, barre, linee, percentuali, KPI, trend, indicatori o aree colorate, imposta contains_chart=true.
- Valori ammessi per chart_type: bar_chart, stacked_bar_chart, line_chart, pie_chart, area_chart, heatmap, gauge, waterfall, scatter_plot, dashboard, process_diagram, org_chart, table_kpi, table_breakdown, unknown_chart.
- Usa chart_type=null SOLO se l'elemento non contiene assolutamente nessun tipo di grafico o visualizzazione dati.
- Per le tabelle NON usare remove_as_layout; valuta solo contains_chart e chart_type.

=== INPUT ===

Pagina: {page_number}

Figure input:
{figures_json}

Tabelle input:
{tables_json}
"""

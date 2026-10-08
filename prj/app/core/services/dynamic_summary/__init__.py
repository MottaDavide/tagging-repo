"""Summary dinamica: aggregazione per quadrupla + analisi espositiva LLM sugli estratti.

A differenza dello step di summary statico (`core.services.summary`, Stage 7 della
pipeline, per-documento), questo servizio è **document-agnostico**: riceve una
serie arbitraria di tag scelti dall'utente, li raggruppa per quadrupla
`(RM, MO, OdC, Ente)` (`grouping`) e produce, per ogni gruppo, un'analisi
espositiva dei soli estratti testuali associati, contestualizzata sulla quadrupla
(`dynamic_summary`). Pensato per essere richiamato sia da CLI sia da una futura API.
"""

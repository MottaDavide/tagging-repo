"""Step di summary: aggregazione tag unici + analisi espositiva LLM per tag.

Vive a valle del tagging. `grouping` raggruppa i tag di un documento per chiave
unica `(RM, MO, OdC, Ente)` (scartando i tag incompleti); `tag_summary` produce
l'analisi espositiva del documento per ogni tag unico.
"""

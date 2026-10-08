"""Statistiche per stadio della pipeline: mutate in-place durante il run, serializzate nell'output."""

from pydantic import BaseModel, field_serializer


class TaggerStats(BaseModel):
    """Statistiche di un run del tagger, mutate in-place e serializzate in `DocumentTaggingOutput`."""

    input_chars: int = 0
    input_tokens: int = 0
    total_pages: int = 0
    llm_calls: int = 0
    llm_time_s: float = 0.0
    n_tag_rm_tags: int = 0
    n_tag_rm_after_postprocess: int = 0
    n_tags_with_mo: int = 0
    n_tags_with_odc: int = 0
    n_tags_no_ente: int = 0
    n_tags_final: int = 0

    @field_serializer("llm_time_s")
    def _round_llm_time(self, value: float) -> float:
        return round(value, 1)

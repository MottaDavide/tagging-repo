"""Conteggio token con tiktoken."""

import tiktoken
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

_TIKTOKEN_ENCODING: str = get_obj_from_config_path("tagging.yaml")["text"]["tokens"]["tiktoken_encoding"]

_tokenizer: tiktoken.Encoding = tiktoken.get_encoding(_TIKTOKEN_ENCODING)


def count_tokens(text: str) -> int:
    """Conta i token di `text` con tiktoken."""
    return len(_tokenizer.encode(text))

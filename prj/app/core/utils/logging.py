"""Logger compatto centralizzato per la pipeline di tagging.

Layout: `{ts}  {level:<8}  {indent}{message}`.
L'indent dipende dal logger name (non dal codice chiamante): il sub-logger
`tagging.genfactory` è indentato di 4 spazi per nestare visivamente i sub-eventi
HTTP sotto le call di stage.
"""

import logging

_LEVEL_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[1;31m",
}
_RESET = "\033[0m"

GENFACTORY_LOGGER_NAME = "tagging.genfactory"
_INDENT_BY_LOGGER = {GENFACTORY_LOGGER_NAME: "    "}


class _CompactFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        level = record.levelname
        color = _LEVEL_COLORS.get(level, "")
        level_str = f"{color}{level:<8}{_RESET}"
        indent = _INDENT_BY_LOGGER.get(record.name, "")
        line = f"{ts}  {level_str}  {indent}{record.getMessage()}"
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            line = f"{line}\n{record.exc_text}"
        if record.stack_info:
            line = f"{line}\n{self.formatStack(record.stack_info)}"
        return line


def setup_logging(name: str = __name__) -> logging.Logger:
    """Configura il root logger e ritorna un logger named."""
    handler = logging.StreamHandler()
    handler.setFormatter(_CompactFormatter())
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    return logging.getLogger(name)

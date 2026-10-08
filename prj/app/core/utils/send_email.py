import functools
import inspect
import logging
import os
import traceback
from collections.abc import Callable
from typing import Any

from bdlpkg.providers.isp.messaging.services.mail import send_mail
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path

_CONFIG = get_obj_from_config_path("mail.yaml")
logger = logging.getLogger(__name__)


def on_error_send_email(content_key: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = inspect.signature(func).bind(*args, **kwargs)
            bound.apply_defaults()
            run_id = bound.arguments.get("run_id")
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                step = getattr(exc, "current_step", "unknown")
                try:
                    EmailHandler(run_id=run_id).send_email_error(
                        _CONFIG[content_key].format(
                            step=step,
                            exception_message=str(exc),
                            traceback="".join(
                                traceback.format_exception(
                                    type(exc),
                                    exc,
                                    exc.__traceback__,
                                )
                            ),
                        )
                    )
                except Exception:
                    logger.exception("Failed to send error email for run_id=%s", run_id)
                raise

        return wrapper

    return decorator


class EmailHandler:
    def __init__(self, run_id: str | None = None):
        self.run_id = run_id
        self.environment = os.getenv("ISP_AMBIENTE", "development")
        self.recipients: list[str] = _CONFIG["email_recipient"]

    def send_email_error(self, content: str) -> bool:
        """
        Send email when error occurs.

        Args:
            content: error content

        Returns:
            True if correctly sent email, False otherwise
        """
        if not self.recipients:
            logger.warning("No email recipient configured.")
            return False
        try:
            send_mail(
                to=self.recipients,
                subject=f"CAO-FAC-TAGGING-{self.environment}",
                content=f"Buongiorno GAIAA developers,\n\n"
                f"Si è verificato un errore nell'ambiente {self.environment}.\n"
                f"Ecco i dettagli dell'errore:\n\n"
                f"{content}\n\n"
                f"Run id: {self.run_id} \n\n"
                f"Vi invitiamo a esaminare il problema il prima possibile.\n\n"
                f"Grazie,\nIl vostro sistema di monitoraggio",
            )
        except Exception:
            logger.exception("Failed to send email for run_id=%s", self.run_id)
            return False
        else:
            logger.info("Successfully sent email for run_id=%s", self.run_id)
            return True

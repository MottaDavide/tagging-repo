import logging
import os
from typing import Any, Literal

import requests
from starlette.status import HTTP_200_OK

from core.models.entities.entities import (
    ClassificationAck,
    ErrorAck,
)

logger = logging.getLogger(__name__)


CALLBACK_ENV_BY_MODE = {
    "tagging": "CALLBACK_TAGGING",
    "summary": "CALLBACK_SUMMARY",
}


def send_ack(
    data: dict[str, Any], mode: Literal["tagging", "summary"], run_id: str | None = None, error: ErrorAck | None = None
) -> None:
    ack = ClassificationAck(
        run_id=run_id,
        error=error,
        data=data,
        message="" if mode == "summary" else None,
    )
    callback_env = CALLBACK_ENV_BY_MODE[mode]
    callback = os.getenv(callback_env)
    ack_payload = ack.model_dump_json(by_alias=True)
    logger.info(ack_payload)

    if callback is not None:
        headers = {"Content-Type": "application/json"}
        try:
            response = requests.post(
                callback,
                data=ack_payload,
                headers=headers,
                timeout=30,
                verify=False,  # noqa: S501
            )
        except requests.RequestException:
            logger.exception("Error while sending ack to CALLBACK for run_id=%s", run_id)
            return

        if response.status_code == HTTP_200_OK:
            logger.info("Ack sent successfully to ITTools for run_id=%s", run_id)
            return

        logger.error(
            "Ack delivery to ITTools failed for run_id=%s. Status=%s, Message=%s",
            run_id,
            response.status_code,
            response.text,
        )
    else:
        logger.warning(
            "Ack delivery to ITTools is disabled: %s is not configured for run_id=%s",
            callback_env,
            run_id,
        )

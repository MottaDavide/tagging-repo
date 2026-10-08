"""Global Exception handlers"""

from fastapi import FastAPI

from api.exceptionhandlers.base import base_exception_handler


def register_exception_handlers(app: FastAPI) -> FastAPI:
    """Register global exception handlers"""
    base_exception_handler(app)

    return app

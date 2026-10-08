"""
Module containing base exception handlers. Generic or common exceptions should be handled here,
unless on of the following condition holds (in that case a custom exception should be handled separately)
Cases for domain specific
*   Adding new fields into the error description which aren't only tied to id and message requiring
    the developer to extend the base error
*   Handling the HTTP response differently, for any reason
"""

from fastapi import FastAPI, Request, status
from starlette.responses import JSONResponse

from api.exceptionhandlers.utils import build_content


def base_exception_handler(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def internal_server_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=build_content("Internal Server Error"),
        )

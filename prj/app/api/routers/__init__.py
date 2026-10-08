from bdlpkg.routers import internal
from fastapi.applications import FastAPI

from . import v1


def register_routers(app: FastAPI) -> FastAPI:
    app.include_router(internal.router, prefix="/v1/internal")
    app.include_router(v1.router, prefix="/v1")
    return app

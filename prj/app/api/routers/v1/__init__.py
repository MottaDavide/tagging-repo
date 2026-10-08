# https://github.com/GArmane/python-fastapi-hex-todo/blob/master/todolist/api/routers/account/__init__.py
from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from fastapi.routing import APIRouter

from . import endpoints

app_configs = get_obj_from_config_path("app.yaml")


def _build_router() -> APIRouter:
    rt = APIRouter(tags=[app_configs["application"]["name"]])
    rt.include_router(endpoints.router, prefix="")

    return rt


router = _build_router()

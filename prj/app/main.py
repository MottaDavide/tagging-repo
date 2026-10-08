import logging
import os

from bdlpkg.utils.bdlfile.services.bdlfile import get_obj_from_config_path
from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from fastapi.staticfiles import StaticFiles
from genfactory.config import GenfactoryConfig, set_configuration
from genfactory.config.enums import Environment
from starlette.responses import HTMLResponse

from api.exceptionhandlers import register_exception_handlers
from api.routers import register_routers

logger = logging.getLogger(__name__)

app_configs = get_obj_from_config_path("app.yaml")

if "ISP_AMBIENTE" in os.environ:
    STATIC_DIRECTORY = os.path.join(os.getenv("VIRTUAL_ENV", "/opt/app-root"), "com.intesasanpaolo.bdl", "static")
else:
    STATIC_DIRECTORY = os.path.join(os.environ["MY_HOME"], "prj", "static")

if "ISP_AMBIENTE" in os.environ:
    import sys as _sys

    _pkg_module = _sys.modules.get(__package__ or __name__)
    packet_name = str(getattr(_pkg_module, "__package_name__", app_configs["application"]["name"]))
    versione = str(getattr(_pkg_module, "__version__", "unknown"))
    title = packet_name
else:
    versione = f"dev {os.getenv('USER', os.getenv('USERNAME', 'localuser'))}@{os.getenv('HOSTNAME', os.getenv('COMPUTERNAME', 'localuser'))}"
    title = app_configs["application"]["name"]

tags_metadata = app_configs["tags_metadata"]
tags_metadata.insert(0, {"name": app_configs["application"]["name"], "description": app_configs["short_description"]})

if "ISP_AMBIENTE" in os.environ:
    env_dispatcher = (
        Environment.PRODUCTION if os.environ["ISP_AMBIENTE"] in {"svil", "test", "prod"} else Environment.TEST
    )
else:
    logger.warning("There is no isp ambiente, layer set to TEST")
    env_dispatcher = Environment.TEST

set_configuration(
    GenfactoryConfig(
        use_case_id=get_obj_from_config_path("llm.yaml")["layer"]["use_case_id"],
        env=env_dispatcher,
        enable_self_authentication=True,
    )
)


app = FastAPI(
    title=title,
    description=app_configs["description"],
    openapi_tags=tags_metadata,
    version=versione,
    docs_url=None,
    redoc_url=None,
)

swagger_ui_oauth2_redirect_url = app.swagger_ui_oauth2_redirect_url or "/docs/oauth2-redirect"

try:
    app.mount("/static", StaticFiles(directory=STATIC_DIRECTORY), name="static")
except Exception:
    logger.warning("No static path")


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html() -> HTMLResponse:
    return get_swagger_ui_html(
        openapi_url="./openapi.json",
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=swagger_ui_oauth2_redirect_url,
        swagger_js_url="./static/swagger-ui-bundle.js",
        swagger_css_url="./static/swagger-ui.css",
        swagger_favicon_url="./static/LogoBdL.jpg",
    )


@app.get(swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect() -> HTMLResponse:
    return get_swagger_ui_oauth2_redirect_html()


register_exception_handlers(app)
register_routers(app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        port=8000,
        reload=True,
        app_dir=os.path.join(os.getenv("MY_HOME", ""), "prj", "dir"),
        log_config=os.path.join(os.getenv("MY_HOME", ""), "prj", "config", "uvicorn_conf.yaml"),
    )

import multiprocessing
import os

# https://stackoverflow.com/questions/61582566/fastapi-gunicorn-add-a-logging-timestamp
# https://docs.python.org/3/library/logging.config.html#configuration-dictionary-schema

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "formatters": {
        "default": {
            "format": "%(asctime)s %(levelname)s [%(module)s] (%(threadName)s) %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S.000%z",
        }
    },
    "handlers": {
        "console": {
            "formatter": "default",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "level": os.getenv("LOG_LEVEL", "info").upper(),
        }
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
        "gunicorn.access": {
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
        "gunicorn.error": {
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
        "gunicorn": {
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
        "uvicorn": {
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
        "__main__": {  # if __name__ == '__main__'
            "handlers": ["console"],
            "level": os.getenv("LOG_LEVEL", "info").upper(),
            "propagate": False,
        },
    },
}

# https://docs.gunicorn.org/en/20.1.0/design.html#how-many-workers
workers_per_core_str = os.getenv("WORKERS_PER_CORE", "2")
max_workers_str = os.getenv("MAX_WORKERS")
timeout = os.getenv("WORKER_TIMEOUT", "30")
use_max_workers = None
if max_workers_str:
    use_max_workers = int(max_workers_str)
web_concurrency_str = os.getenv("WEB_CONCURRENCY", None)
cores = multiprocessing.cpu_count()
workers_per_core = float(workers_per_core_str)
default_web_concurrency = workers_per_core * cores
if web_concurrency_str:
    web_concurrency = int(web_concurrency_str)
    assert web_concurrency > 0
else:
    web_concurrency = max(int(default_web_concurrency), 2)
    if use_max_workers:
        web_concurrency = min(web_concurrency, use_max_workers)

# Gunicorn config variables
# https://docs.gunicorn.org/en/20.1.0/settings.html

accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
errorlog = "-"
logconfig_dict = LOG_CONFIG
logger_class = "gunicorn.glogging.Logger"
disable_redirect_access_to_syslog = True
bind = os.getenv("BIND", "0.0.0.0:9222")
workers = web_concurrency
enable_stdio_inheritance = True

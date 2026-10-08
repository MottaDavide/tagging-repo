#! /usr/bin/env sh
set -x

confdir="${VIRTUAL_ENV}/com.intesasanpaolo.bdl/prj-config"

export PY_VER="$(python --version | grep -oP '\d+\.\d+')"

export BDL_APP_NAME=$(echo ${ARTIFACT_URL} | rev | cut -d '/' -f 1 | rev | cut -d '-' -f 1 | sed 's/_/-/g')
export PYTHONPATH="${VIRTUAL_ENV}/lib64/python${PY_VER}/site-packages/${BDL_APP_NAME}"
export PYTHONUNBUFFERED=1 # https://docs.python.org/3/using/cmdline.html#cmdoption-u

echo confdir is ${confdir}
echo "Starting $BDL_APP_NAME using $(python --version)"

# Start Gunicorn
exec gunicorn -k "uvicorn.workers.UvicornWorker" -c "${confdir}/gunicorn_conf.py" $BDL_APP_NAME.main:app

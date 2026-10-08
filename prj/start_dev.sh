#! /usr/bin/env sh
set -ex

HOST=${HOST:-0.0.0.0}
user=$(whoami)
userPort="4${user:3:10}"
PORT=${PORT:-$userPort}
LOG_LEVEL=${LOG_LEVEL:-info}

workdir="$(pwd)/prj"
confdir="$(pwd)/prj/config"

export PYTHONDONTWRITEBYTECODE=1
export APP_CONF_DIR="$(pwd)/prj/app/config"
export DS_CONF_DIR=$APP_CONF_DIR
export MY_HOME="$(pwd)"

#Uvicorn
cd $workdir
exec uvicorn --host $HOST  --port $PORT --log-level $LOG_LEVEL  --app-dir "${workdir}/app" --log-config "${workdir}/config/uvicorn_conf.yaml" "main:app"

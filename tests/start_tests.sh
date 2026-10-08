#! /usr/bin/env sh

workdir="$(pwd)/prj"

export PYTHONDONTWRITEBYTECODE=1
export APP_CONF_DIR="$(pwd)/prj/app/config"
export DS_CONF_DIR=$APP_CONF_DIR
export MY_HOME="$(pwd)"

export PYTHONPATH="${workdir}/app"

pytest \
    --metadata user $(whoami) \
    --continue-on-collection-errors  \
    --junit-xml="tests/results.xml"  \
    --html="tests/report.html" --self-contained-html \
    --cov="${workdir}/app" --cov-report=html --cov-report term-missing\
    "$(pwd)/tests/plan"

echo "tests report: $(pwd)/tests/report.html"
echo "coverage report: $(pwd)/htmlcov/index.html"

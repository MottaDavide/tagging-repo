#!/bin/bash

#set -x

usage() { echo "Usage: $0 -c <new|install> [-v <3.9|3.11|3.12> default: '3.9'] [-p <path> default: './'] [-n <venv name> default: 'venv'] [-r <requirements file> default: './requirements.txt']" 1>&2; exit 1; }

v="3.9"
n="venv"
p="./"
r="./requirements.txt"

while getopts ":c:v:p:n:r:" o; do
    case "${o}" in
        c)
            c=${OPTARG}
            [[ ${c} == "new" || ${c} == "install" ]] || usage
            ;;
        v)
            v=${OPTARG}
            [[ ${v} == "3.9" || ${v} == "3.11" || ${v} == "3.12" ]] || usage
            ;;
        p)
            p=${OPTARG}
            ;;
        n)
            n=${OPTARG}
            ;;
        r)
            r=${OPTARG}
            ;;
        *)
            usage
            ;;
    esac
done
shift $((OPTIND-1))

if [ -z "${c}" ]; then
    usage
fi

userid=$(whoami)

case "${v}" in
    3.9)
        if [ ! -z "${WINDIR}" ]; then
            python_win_path="/c/users/${userid}/AppData/Local/Programs/Python/Python39"
            echo "using windows python $python_win_path"
            if [ -d $python_win_path ]; then
                local_python="${python_win_path}/python"
            fi
        else
            local_python=$(which python) #eseguire "pyenv shell 3.9.7" prima dell'esecuzione di questo script per cambiare riferimento di python affichè punti a 3.9
        fi
        ;;
    3.11)
        if [ ! -z "${WINDIR}" ]; then
            python_win_path="/c/users/${userid}/AppData/Local/Programs/Python/Python311"
            echo "using windows python $python_win_path"
            if [ -d $python_win_path ]; then
                local_python="${python_win_path}/python"
            fi
        else
            local_python=$(which python3)
        fi
        ;;
    3.12)
        if [ ! -z "${WINDIR}" ]; then
            python_win_path="/c/users/${userid}/AppData/Local/Programs/Python/Python312"
            echo "using windows python $python_win_path"
            if [ -d $python_win_path ]; then
                local_python="${python_win_path}/python"
            fi
        else
            local_python=$(which python312)
        fi
        ;;
esac

echo "using python in ${local_python}"

mk_venv(){
    DIR="${p}${n}"
    if [ ! -d "$DIR" ]; then
        echo "New venv in ${DIR}..."
        $local_python -m venv ${p}${n}
    else
        echo "Error: venv in ${DIR} exists. Can not continue."
        exit 1
    fi
}

install_requirements(){
    FILE="${r}"
    if [ -f "${FILE}" ]; then
        if [ ! -z "${VIRTUAL_ENV}" ]; then
            #TODO da chhiedere Utenza e psasswrd all'utente + profilazione arti
            pip install -i https://snapshot-deployer:snapshot@arti0-artifactory.sede.corp.sanpaoloimi.com/artifactory/api/pypi/pypi-repos/simple/ --trusted-host arti0-artifactory.sede.corp.sanpaoloimi.com \
                --upgrade pip setuptools mypy yapf notebook --no-cache-dir
            pip install -r ${FILE} \
                -i https://snapshot-deployer:snapshot@arti0-artifactory.sede.corp.sanpaoloimi.com/artifactory/api/pypi/pypi-repos/simple/ \
                --trusted-host arti0-artifactory.sede.corp.sanpaoloimi.com --no-cache-dir
        else
            echo "Error: Ooops! Can not continue. Please run your venv first! "
            echo "Tip! Run 'source ${p}${n}/bin/activate' to enable the new venv! (linux)"
            echo "Tip! Run 'source ${p}${n}/Scripts/activate' to enable the new venv! (windows)"
            exit 1
        fi
    else
        echo "Error: ${FILE} not available. Can not continue."
        exit 1
    fi
}

case "${c}" in
    new)
        mk_venv
        echo "Tip! Run 'source ${p}${n}/bin/activate' to enable the new venv! (linux)"
        echo "Tip! Run 'source ${p}${n}/Scripts/activate' to enable the new venv! (windows)"
        ;;
    install)
        install_requirements
        ;;
esac

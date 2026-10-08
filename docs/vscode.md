# VScode

Qui potrai trovare alcuni consigli utili per utilizzare al meglio il coolpkg in VScode.

## Impostazioni

Si raccomanda di disattivare le telemetrie di vscode e di tutti i plugin installati. Puoi cercare `telemetry` in `File > Preferences > Settings`

Maggiori informazioni nella sezione delle documentazione ['dedicata'](https://code.visualstudio.com/docs/getstarted/settings).

Inoltre, per usare al meglio coolpkg, puoi aggiungere le seguenti configurazioni:

``` json
{
    "telemetry.telemetryLevel": "off",
    "editor.formatOnSave": true,
    "python.envFile": "${workspaceFolder}/venv",
    "python.formatting.provider": "yapf",
    "python.linting.mypyEnabled": true,
    "python.linting.mypyArgs": [
        "--config-file=${workspaceFolder}/setup.cfg"
    ],
    "python.autoComplete.extraPaths": [
        "${workspaceFolder}/prj/app"
    ],
    "python.analysis.extraPaths": [
        "${workspaceFolder}/prj/app"
    ]
}
```

Il file json delle configurazioni puoi aprilo con il comando `Ctrl + Shift + P` cercando `Preferences: Open Settings (Json)`

## Formatter

Nel file `setup.cfg` sono disponibili le impostazioni per `yapf`. Ricordati di formatatre i documenti prima di versionare il tuo codice.

## Linting

Per il type hints e il controllo statico, nel file `setup.cfg`, sono disponibili le impostazioni per `mypy` scelte per il coolpkg.

Mentre scrivi il tuo codice, assicurati di non avere notifiche nella sezione **PROBLEMS** di vscode.

## DEBUG

Per eseguire il debug, abbiamo preparato le configurazioni base di debug per il coolpkg.
Puoi inserire il seguente json in `.vscode/launch.json`

``` json
{
    // Use IntelliSense to learn about possible attributes.
    // Hover to view descriptions of existing attributes.
    // For more information, visit: https://go.microsoft.com/fwlink/?linkid=830387
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Current File",
            "type": "debugpy",
            "request": "launch",
            "program": "${file}",
            "console": "integratedTerminal"
        },
        {
            "name": "RUN APP",
            "type": "debugpy",
            "request": "launch",
            "module": "uvicorn",
            "args": [
                "--app-dir",
                "app",
                "--log-config",
                "config/uvicorn_conf.yaml",
                "--port",
                "9999",
                "--host",
                "0.0.0.0",
                "main:app"
            ],
            "jinja": true,
            "cwd": "${workspaceFolder}/prj",
            "env": {
                "MY_HOME": "${workspaceFolder}",
                "APP_CONF_DIR": "${workspaceFolder}/prj/app/config",
                "DS_CONF_DIR": "${workspaceFolder}/prj/app/config"
            }
        },
        {
            "name": "RUN TEST from current unittest",
            "type": "debugpy",
            "request": "launch",
            "module": "pytest",
            "args": [
                "--continue-on-collection-errors",
                "${file}"
            ],
            "jinja": true,
            "cwd": "${workspaceFolder}",
            "env": {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPATH": "${workspaceFolder}/prj/app",
                "MY_HOME": "${workspaceFolder}",
                "APP_CONF_DIR": "${workspaceFolder}/prj/app/config",
                "DS_CONF_DIR": "${workspaceFolder}/prj/app/config"
            }
        }
    ]
}
```

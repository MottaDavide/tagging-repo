import os

import setuptools  # type: ignore
from yaml import safe_load

"""
- I file YAML sono dentro VENV/com.intesasanpaolo.bdl/ quindi è da cambiare il BDLPKG dove va a prendersi i file isp-config-env... MYHOME diventa com.intesasanpaolo.com?
"""

# region CONFIG
ENTRY_POINT = "prj"
BDL_NAME = "com.intesasanpaolo.bdl"
CONFIG_PATH = "prj/app/config/app.yaml"
# endregion

# region LOAD

with open(CONFIG_PATH) as f:
    CONFIG_DICT = safe_load(f)

# TODO: create a file with info taken using gitpython | Metterei l'autore dell'ultimo commit

with open("README.md", encoding="utf-8") as fh:
    long_description = fh.read()

# https://github.com/kubernetes-client/python/blob/master/setup.py
REQUIRES = []
with open("requirements.txt", encoding="utf-8") as f:
    for line in f:
        line, _, _ = line.partition("#")
        line = line.strip()
        if len(line) > 0 and not line.startswith((".", "/")):
            REQUIRES.append(line)

_docs = setuptools.find_packages(where=ENTRY_POINT)

for root, dirs, _ in os.walk(os.path.join(ENTRY_POINT, "app"), topdown=True, followlinks=False):
    for name in dirs:
        _path = os.path.join(root.replace(ENTRY_POINT + os.path.sep, ""), name).replace(os.path.sep, ".")
        _docs.append(_path)

print(f"---------PACCHETTI {setuptools.find_packages(where=ENTRY_POINT)}")  # noqa: T201
_docs = list(set(_docs))

print(_docs)  # noqa: T201
# endregion

# region EXTRA FILES

extra_files = [
    (
        f"{BDL_NAME}/isp-config-env",
        [f"isp-config-env/configuration{tipo}.yml" for tipo in ["", "-svil", "-test", "-prod", "-svis", "-ptes"]],
    ),
    (f"{BDL_NAME}/prj-config", setuptools.findall(os.path.join(ENTRY_POINT, "config"))),  # pyright: ignore[reportAttributeAccessIssue]
    (f"{BDL_NAME}/startup", [r"prj/start.sh", r"prj/start_dev.sh"]),
]

static_root = os.path.join(ENTRY_POINT, "static")
for dirpath, _, filenames in os.walk(static_root):
    if filenames:
        relative_dir = os.path.relpath(dirpath, ENTRY_POINT)
        files = [os.path.join(dirpath, f) for f in filenames]
        extra_files.append((os.path.join(BDL_NAME, relative_dir), files))

# sotto cartelle dell'app config - voglio solo ultima directory

parte_conf = []
for root, _dirs, files in os.walk(os.path.join(ENTRY_POINT, "app", "tiktoken_cache")):
    parte_conf.append((f"{BDL_NAME}/tiktoken_cache", [os.path.join(root, file) for file in files]))

extra_files = extra_files.__add__(parte_conf)


parte_config = [
    (
        f"{BDL_NAME}{d.replace('app.config', '/app-config/prj/app/config').replace('.', '/')}",  # TODO: Fix in BDLPKG così non devo fare questo giro perché ora devo mettere un MY_HOME con dentro un prj/app/config e quindi metto MY_HOME="/opt/app-root/com.intesasanpaolo.bdl/app-config" nelle configurazioni. A regime mettere il puntamento per app-config
        [
            f
            for f in setuptools.findall(os.path.join(ENTRY_POINT, d.replace(".", os.path.sep)))  # pyright: ignore[reportAttributeAccessIssue]
            if f.split(os.path.sep)[-2] == d.split(".")[-1]
        ],
    )
    for d in _docs
    if "app.config" in d
]
print("CONFIGS ", end="")  # noqa: T201
print(parte_config)  # noqa: T201
extra_files = extra_files.__add__(parte_config)
# region

NAME = os.environ["REPO_NAME"]

setuptools.setup(
    name=NAME,
    version=os.environ["VERSION"],
    author="BDL",
    # author_email="bdl-tds@intesasanpaolo.com",
    # description=CONFIG_DICT["short_description"],
    long_description=long_description,
    long_description_content_type="text/markdown",
    # url="https://bitbucket.intesasanpaolo.com/scm/bdl10-svil/bdl10-coolpkg.git",
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
    data_files=extra_files,
    package_dir={
        n.replace("app", NAME): os.path.join(ENTRY_POINT, n.replace(".", os.path.sep))
        for n in _docs  # setuptools.find_packages(where=ENTRY_POINT)
        if len(n) > 0 and "app.config" not in n
    },
    # packages=setuptools.find_packages(where=ENTRY_POINT),
    include_package_data=False,  # True means that all versionned files will be included if not explicitly excluded @ https://stackoverflow.com/questions/8556996/setuptools-troubles-excluding-packages-including-data-files - fix che sono doppie le config, sia in com.../app-config che in coolpkg/config
    python_requires=">=3.8",
    install_requires=REQUIRES,
)

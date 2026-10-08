def get_version_package() -> tuple[str, str]:
    try:
        from importlib.metadata import distribution

        dist = distribution(__name__)
        __version__ = dist.version
        __package_name__ = dist.metadata["Name"]
    except Exception:
        __version__ = "unknown"
        __package_name__ = "unknown"
    return __version__, __package_name__


__version__, __package_name__ = get_version_package()

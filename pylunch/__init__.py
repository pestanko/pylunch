def get_version():
    import toml
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'pyproject.toml'
    if path.exists():
        pyproject = toml.loads(open(str(path)).read())
        return pyproject['tool']['poetry']['version']
    else:
        import pkg_resources
        return pkg_resources.get_distribution("pylunch").version

__version__ = get_version()
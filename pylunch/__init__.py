def get_version():
    import toml
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'pyproject.toml'
    pyproject = toml.loads(open(str(path)).read())
    return pyproject['tool']['poetry']['version']

__version__ = get_version()
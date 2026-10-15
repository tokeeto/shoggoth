"""Every module imports, and the command line starts.

Cheap insurance against the classic "works on my machine" release breakage:
a typo'd import, a module deleted while something still imports it, a
syntax error in a dialog nobody opened before releasing.
"""
import importlib
import pkgutil
import subprocess
import sys

import pytest

import shoggoth

MODULES = sorted(
    info.name for info in pkgutil.walk_packages(shoggoth.__path__, 'shoggoth.')
    # launched as scripts, with side effects on import
    if info.name not in ('shoggoth.__main__', 'shoggoth.run', 'shoggoth.launcher')
)


@pytest.mark.parametrize('module', MODULES)
def test_module_imports(module):
    importlib.import_module(module)


def test_cli_help():
    # the `shoggoth` console script's entry point (pyproject.toml)
    code = 'import sys; sys.argv = ["shoggoth", "--help"]; from shoggoth.tool import run; run()'
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert '--render' in result.stdout

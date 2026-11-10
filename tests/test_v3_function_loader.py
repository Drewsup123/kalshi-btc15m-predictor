"""Load pytest-style test_v3_* functions into unittest."""

from __future__ import annotations

import importlib
import inspect
from pathlib import Path
import unittest


def _wrap(fn):
    def test(self):
        fn()

    test.__name__ = fn.__name__
    test.__doc__ = fn.__doc__
    return test


class V3FunctionTests(unittest.TestCase):
    pass


_root = Path(__file__).resolve().parent
for _path in sorted(_root.glob("test_v3_*.py")):
    if _path.name == "test_v3_function_loader.py":
        continue
    _mod = importlib.import_module(f"tests.{_path.stem}")
    for _name, _fn in inspect.getmembers(_mod, inspect.isfunction):
        if _name.startswith("test_"):
            setattr(V3FunctionTests, f"{_path.stem}__{_name}", _wrap(_fn))

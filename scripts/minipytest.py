"""Tiny pytest stand-in for sandboxes where pytest cannot be installed (no network).

NOT a replacement for pytest. It supports exactly what this repo's tests use: plain test functions,
`@pytest.fixture` (including conftest.py fixtures), `pytest.raises`, `pytest.skip`, `pytest.mark.skipif`,
`tmp_path` and `monkeypatch`. Anything else fails loudly. Confirm results locally with `python -m pytest -q`.

Usage: python scripts/minipytest.py [-k SUBSTRING] [tests/test_x.py ...]
"""
from __future__ import annotations
import importlib.util
import inspect
import os
import shutil
import sys
import tempfile
import time
import traceback
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))


class Skipped(Exception):
    pass


class _Raises:
    def __init__(self, exc, match=None):
        self.exc, self.match, self.value = exc, match, None

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            raise AssertionError(f"DID NOT RAISE {self.exc}")
        if not issubclass(et, self.exc):
            return False
        if self.match:
            import re
            if not re.search(self.match, str(ev)):
                raise AssertionError(f"exception text {str(ev)!r} does not match {self.match!r}")
        self.value = ev
        return True


class _Mark:
    def skipif(self, cond, reason=""):
        def deco(fn):
            fn.__skip__ = reason if cond else None
            return fn
        return deco

    def __getattr__(self, name):
        raise AttributeError(f"pytest.mark.{name} is not supported by minipytest")


class MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def setenv(self, k, v):
        self._undo.append((os.environ, k, os.environ.get(k)))
        os.environ[k] = v

    def delenv(self, k, raising=True):
        if k not in os.environ:
            if raising:
                raise KeyError(k)
            return
        self._undo.append((os.environ, k, os.environ[k]))
        del os.environ[k]

    def undo(self):
        for obj, name, old in reversed(self._undo):
            if obj is os.environ:
                (os.environ.pop(name, None) if old is None else os.environ.__setitem__(name, old))
            else:
                setattr(obj, name, old)


def _install_fake_pytest():
    m = types.ModuleType("pytest")
    m.fixture = lambda fn=None, **kw: (setattr(fn, "__fixture__", True) or fn) if fn else (lambda f: (setattr(f, "__fixture__", True) or f))
    m.raises = lambda exc, match=None: _Raises(exc, match)
    m.mark = _Mark()

    def skip(reason=""):
        raise Skipped(reason)
    m.skip = skip
    m.approx = lambda v, rel=1e-6, abs=1e-12: _Approx(v, rel, abs)
    sys.modules["pytest"] = m


class _Approx:
    def __init__(self, v, rel, abs_):
        self.v, self.rel, self.abs = v, rel, abs_

    def __eq__(self, o):
        return abs(o - self.v) <= max(self.rel * abs(self.v), self.abs)


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


def main(argv):
    _install_fake_pytest()
    sel = [a for a in argv if not a.startswith("-")]
    kfilter = argv[argv.index("-k") + 1] if "-k" in argv else None
    if kfilter in sel:
        sel.remove(kfilter)
    files = [Path(s) for s in sel] or sorted((ROOT / "tests").glob("test_*.py"))
    conf = _load(ROOT / "tests" / "conftest.py")
    fixtures = {n: f for n, f in vars(conf).items() if getattr(f, "__fixture__", False)}
    passed = failed = skipped = 0
    t0 = time.time()
    for f in files:
        mod = _load(f.resolve())
        local_fx = {n: fn for n, fn in vars(mod).items() if getattr(fn, "__fixture__", False)}
        for name, fn in sorted(vars(mod).items()):
            if not (name.startswith("test_") and callable(fn)):
                continue
            if kfilter and kfilter not in name:
                continue
            if getattr(fn, "__skip__", None) is not None:
                skipped += 1
                continue
            cleanups, kwargs = [], {}
            try:
                for p in inspect.signature(fn).parameters:
                    if p == "tmp_path":
                        d = tempfile.mkdtemp(prefix="minipytest_")
                        cleanups.append(lambda d=d: shutil.rmtree(d, ignore_errors=True))
                        kwargs[p] = Path(d)
                    elif p == "monkeypatch":
                        mp = MonkeyPatch()
                        cleanups.append(mp.undo)
                        kwargs[p] = mp
                    elif p in local_fx or p in fixtures:
                        kwargs[p] = (local_fx.get(p) or fixtures[p])()
                    else:
                        raise RuntimeError(f"unsupported fixture {p!r}")
                fn(**kwargs)
                passed += 1
            except Skipped:
                skipped += 1
            except Exception:
                failed += 1
                print(f"FAILED {f.name}::{name}\n{traceback.format_exc()}")
            finally:
                for c in cleanups:
                    c()
    print(f"{passed} passed, {failed} failed, {skipped} skipped in {time.time() - t0:.1f}s  (minipytest: run `python -m pytest -q` to confirm)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

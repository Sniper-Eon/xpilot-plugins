"""Plugin tests run against an xpilot checkout on PYTHONPATH (see CONTRIBUTING.md). Without the compiled
openpilot/common/libparams_c.so (CI, a fresh checkout) a do-nothing Params stands in."""
import sys
import types

try:
  import openpilot.common.params  # noqa: F401
except Exception:
  class Params:
    def __init__(self, *a, **k): pass
    def get_bool(self, *a, **k): return False
    def get(self, *a, **k): return None
    def put(self, *a, **k): pass
    def put_bool(self, *a, **k): pass

  sys.modules["openpilot.common.params"] = types.SimpleNamespace(Params=Params, ParamKeyType=types.SimpleNamespace(),
                                                                 UnknownKeyName=KeyError)

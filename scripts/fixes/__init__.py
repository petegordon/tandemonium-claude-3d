"""Fix plugins: small, per-character corrections applied to a mesh/texture in a pipeline stage.

A plugin is a module in this package defining:
    NAME      str   unique id used in configs / CLI
    STAGE     str   pipeline stage it runs in: "hi" (clean_hi.py, before export)
    DEFAULTS  dict  parameter defaults (JSON-serialisable)
    apply(ctx: FixContext, **params) -> dict   stats to record

Which fixes run, and with what params, comes from chars/<char>.json:
    {"fixes": [{"fix": "hat_recolor", "z_frac": 0.88}]}
plus CLI additions (--fix name or --fix name:key=value,key=value).
"""
import importlib
import re
import json
import pkgutil
from pathlib import Path

from .common import FixContext  # noqa: F401  (re-export)


def registry():
    out = {}
    for m in pkgutil.iter_modules(__path__):
        if m.name == "common" or m.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{m.name}")
        if hasattr(mod, "NAME") and hasattr(mod, "apply"):
            out[mod.NAME] = mod
    return out


def parse_cli(spec):
    """'trim_fins:z_frac=[0,0.06],seed_mm=5' -> {'fix': 'trim_fins', 'z_frac': [0, 0.06], ...}
    (commas inside [...] belong to list values)"""
    name, _, rest = spec.partition(":")
    out = {"fix": name}
    for kv in filter(None, re.split(r",(?![^\[]*\])", rest)):
        k, _, v = kv.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    return out


def load_config(root, char):
    p = Path(root) / "chars" / f"{char}.json"
    return json.loads(p.read_text()) if p.exists() else {}


def run(ctx, specs, stage):
    reg = registry()
    results = []
    for spec in specs:
        spec = dict(spec)
        name = spec.pop("fix")
        if spec.pop("enabled", True) is False:
            continue
        mod = reg.get(name)
        if mod is None:
            raise KeyError(f"unknown fix '{name}'; available: {sorted(reg)}")
        if mod.STAGE != stage:
            continue
        unknown = set(spec) - set(mod.DEFAULTS)
        if unknown:
            raise KeyError(f"fix '{name}' has no params {sorted(unknown)}; known: {sorted(mod.DEFAULTS)}")
        params = {**mod.DEFAULTS, **spec}
        print(f"[fix] {name} {json.dumps(params)}", flush=True)
        res = mod.apply(ctx, **params)
        results.append({"fix": name, "params": params, "result": res})
        print(f"[fix] {name} -> {json.dumps(res)}", flush=True)
    return results

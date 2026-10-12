#!/usr/bin/env python3
"""Строгая проверка фронтматтера: дубликаты ключей ЛЮБОГО уровня = ошибка."""
import re, sys, pathlib, yaml

class Strict(yaml.SafeLoader):
    pass

def _no_dup(loader, node, deep=False):
    mapping = {}
    for k, v in node.value:
        key = loader.construct_object(k, deep=deep)
        if key in mapping:
            raise ValueError(f"duplicate key: {key!r}")
        mapping[key] = loader.construct_object(v, deep=deep)
    return mapping

Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)

def check(path):
    t = pathlib.Path(path).read_text(encoding='utf-8')
    m = re.match(r'^---\n(.*?)\n---\n', t, re.S)
    if not m:
        return "нет фронтматтера"
    try:
        yaml.load(m.group(1), Loader=Strict)
        return None
    except Exception as e:
        return str(e).splitlines()[0]

if __name__ == "__main__":
    bad = 0
    for p in sys.argv[1:]:
        err = check(p)
        print(("✗ " if err else "✓ ") + p + (f"  → {err}" if err else ""))
        bad += bool(err)
    sys.exit(1 if bad else 0)

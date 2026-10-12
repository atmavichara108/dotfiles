#!/usr/bin/env python3
"""Строгая проверка фронтматтера агентских .md.

Ловит три класса дефектов, каждый из которых уже приводил к тому, что агент
становился невидимым («Unknown agent»):
  1. дубликаты ключей любого уровня (строгий YAML падает, определение
     отбрасывается целиком);
  2. недопустимые значения эффектов прав (допустимо ровно: allow, deny, ask);
  3. хвостовые запятые в значениях — в блочном YAML это часть строки
     (`deny,` вместо `deny`), т.е. недопустимый эффект, который pyyaml
     молча принимает как валидную строку.

usage: agent-yaml-check.py <файл.md> [ещё файлы...]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

VALID_EFFECTS = {"allow", "deny", "ask"}


class Strict(yaml.SafeLoader):
    """Loader, который падает на дубликатах ключей (pyyaml по умолчанию молчит)."""


def _no_dup(loader: Strict, node, deep: bool = False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ValueError(f"дубликат ключа: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


Strict.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_dup)


def _frontmatter(path: Path) -> str | None:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else None


def _bad_effects(obj, path: str = "") -> list[str]:
    bad: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            bad += _bad_effects(value, f"{path}/{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            bad += _bad_effects(value, f"{path}[{i}]")
    elif isinstance(obj, str) and obj not in VALID_EFFECTS and re.fullmatch(r"[a-z]+,?", obj):
        bad.append(f"{path}={obj!r}")
    return bad


def _trailing_commas(fm: str) -> list[str]:
    return [
        ln.strip()
        for ln in fm.splitlines()
        if re.search(r':\s*(allow|deny|ask)\s*,\s*$', ln)
    ]


def check(path_str: str) -> str | None:
    path = Path(path_str)
    fm = _frontmatter(path)
    if fm is None:
        return "нет фронтматтера"
    try:
        data = yaml.load(fm, Loader=Strict)
    except Exception as exc:  # noqa: BLE001
        return str(exc).splitlines()[0]
    commas = _trailing_commas(fm)
    if commas:
        return f"хвостовые запятые в значениях: {len(commas)} шт., напр. {commas[0]!r}"
    bad = _bad_effects(data.get("permission") or {}, "permission")
    if bad:
        return f"недопустимые значения эффектов: {bad[:3]}"
    if not data.get("mode"):
        return "нет mode"
    if not data.get("model"):
        return "нет model"
    return None


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    failed = 0
    for path in argv:
        err = check(path)
        print(("✗ " if err else "✓ ") + path + (f"  → {err}" if err else ""))
        failed += bool(err)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

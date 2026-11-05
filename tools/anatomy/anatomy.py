#!/usr/bin/env python3
"""anatomy — генератор «анатомии Корабля» (производная, read-first).

Мандат ЦУ ref `ic-anatomy-generator`: генерабельная проекция поверх
первоисточников. Никаких записей в чужие реестры (Р-056): пишем только в свою
зону `~/dotfiles/logs/anatomy/`.

Схема (по исследованию ИПТ, канон за словом владельца):
  id / name / shadow / class / zone / boundary / owner / links / state /
  mandate-source + производный служебный блок (ssot:false, derived, sources).

Гейты (пилот):
  - полнота: объект без обязательного поля = дефект слоя;
  - драфт: возраст первоисточника > STALE_DAYS = пометка «модель устарела»;
  - честность: производное помечено ssot:false, первоисточник всегда в sources.

Источники (read-first):
  - реестр манифестов: OpenCode-Vault/docs/org/manifest-registry.md;
  - манифесты:           OpenCode-Vault/docs/org/<id>.md (YAML-frontmatter);
  - peer-registry:       OpenCode-Vault/04-Memory/peer-registry.md (пилот — адреса).

Использование:
  anatomy.py build [--limit 10] [--dry-run]
  anatomy.py show
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml

HOME = Path.home()
DOT = HOME / "dotfiles"
VAULT = HOME / "Projects/OpenCode-Vault"
REGISTRY = VAULT / "docs/org/manifest-registry.md"
ORG_DIR = VAULT / "docs/org"
OUT_DIR = DOT / "logs/anatomy"
OUT_JSONL = OUT_DIR / "anatomy.jsonl"
OUT_MD = OUT_DIR / "anatomy.md"

STALE_DAYS = 7
DEFAULT_LIMIT = 10
REQUIRED = ["id", "name", "class", "zone", "boundary", "owner",
            "links", "state", "mandate_source"]


def _norm(v) -> str:
    if v is None:
        return ""
    return " ".join(str(v).split()).strip()


def _listish(v):
    if v is None:
        return []
    if isinstance(v, list):
        return [_norm(x) for x in v]
    s = _norm(v)
    return [s] if s else []


def _registry_ids(path: Path):
    """[(id, manifest_relpath, registry_line)] из реестра манифестов."""
    out = []
    if not path.exists():
        return out
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        m = re.search(r"`([a-z0-9][a-z0-9_-]*)`", cells[0])
        if not m:
            continue
        oid = m.group(1)
        manifest_rel = None
        mm = re.search(r"`([^`]+\.md)`", cells[3]) if len(cells) > 3 else None
        if mm:
            manifest_rel = mm.group(1)
        elif cells[3].startswith("[[") and cells[3].endswith("]]"):
            manifest_rel = f"docs/org/{oid}.md"
        out.append((oid, manifest_rel, f"manifest-registry.md:{n}"))
    return out


def _read_frontmatter(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    try:
        data = yaml.safe_load(m.group(1))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 — битый frontmatter ≠ дефект генератора
        return {}


def _classify(oid: str, fm: dict, registry_line: str) -> str:
    cl = _norm(fm.get("class"))
    if cl:
        return cl
    blob = " ".join([oid, _norm(fm.get("name")), _norm(fm.get("shadow")), registry_line]).lower()
    if "отдел" in blob:
        return "отдел"
    if "кафедра" in blob:
        return "кафедра"
    if "центр" in blob:
        return "центр"
    if "служба" in blob:
        return "служба"
    if re.search(r"\bагент\b", blob) or "смотритель" in blob or "servant" in blob:
        return "агент"
    return "ведомство"


def _row(oid, manifest_rel, reg_loc):
    path = ORG_DIR / f"{oid}.md"
    manifest_source = manifest_rel or f"docs/org/{oid}.md"
    fm = _read_frontmatter(path)
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    age = round((time.time() - mtime) / 86400, 1) if mtime else None
    fm_source = _norm(fm.get("spec-home") or "")
    zone = _listish(fm.get("file-zones"))
    zone_value = (zone[0] if zone else str(ORG_DIR / f"{oid}.md"))
    boundary = _norm(fm.get("boundaries"))
    owner = _norm(fm.get("carrier-sessions") or fm.get("owner") or "")
    state = _norm(fm.get("status") or "").split(",")[0].split(" ")[0]
    links = {
        "report_address": _norm(fm.get("report-address") or ""),
        "peer_address": _norm(fm.get("peer-address") or ""),
        "spec_home": fm_source,
        "ports": _norm(fm.get("ports") or ""),
        "file_zones": zone,
        "memory_zones": _listish(fm.get("memory-zones")),
    }
    record = {
        "id": oid,
        "name": _norm(fm.get("name")),
        "shadow": _norm(fm.get("shadow")),
        "class": _classify(oid, fm, reg_loc),
        "zone": zone_value,
        "boundary": boundary,
        "owner": owner,
        "links": links,
        "state": state,
        "mandate_source": _norm(fm.get("mandate-source")),
        # производный служебный блок (честность)
        "ssot": False,
        "derived": True,
        "sources": [
            {"path": manifest_source, "line": str(path)},
            {"path": "docs/org/manifest-registry.md", "line": reg_loc},
        ],
        "source_mtime_days": age,
    }
    defects = []
    for field in REQUIRED:
        val = record.get(field)
        if val in ("", None, [], {}):
            defects.append(field)
    record["defects"] = defects
    record["drift"] = ([f"манифест старше {STALE_DAYS} дней"]
                       if age is not None and age > STALE_DAYS else [])
    return record


def collect(limit: int):
    ids = _registry_ids(REGISTRY)
    if limit:
        ids = ids[:limit]
    return [_row(oid, rel, loc) for oid, rel, loc in ids]


def build(dry_run: bool, limit: int):
    rows = collect(limit)
    by_class = {}
    defects_total = 0
    drifted = 0
    for r in rows:
        by_class[r["class"]] = by_class.get(r["class"], 0) + 1
        if r["defects"]:
            defects_total += len(r["defects"])
        if r["drift"]:
            drifted += 1
    summary = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "anatomy-0.1",
        "objects": len(rows),
        "by_class": by_class,
        "required_fields": REQUIRED,
        "defects": defects_total,
        "drifted": drifted,
        "rc": 2 if defects_total else 0,
    }
    payload = {**summary,
               "rows": [{k: v for k, v in r.items()} for r in rows]}
    if dry_run:
        print(json.dumps(payload, ensure_ascii=False))
        return summary["rc"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with OUT_MD.open("w", encoding="utf-8") as f:
        f.write("# Анатомия Корабля — производная проекция (ssot:false)\n\n")
        f.write(f"собрано: {summary['ts']} · объектов: {summary['objects']} "
                f"· дефектов: {summary['defects']} · дрейф: {summary['drifted']}\n\n")
        f.write("## Состав\n\n")
        for k, v in sorted(by_class.items()):
            f.write(f"- {k}: {v}\n")
        f.write("\n## Объекты\n\n")
        for r in rows:
            z = r["zone"]
            f.write(f"- [{r['id']}] {r['name'] or '(без имени)'} "
                    f"(class={r['class']}, state={r['state']}, zone={z}) "
                    f"defects={','.join(r['defects']) or 'нет'} "
                    f"drift={','.join(r['drift']) or 'нет'}\n")
    print(json.dumps(summary, ensure_ascii=False))
    print(f"-> {OUT_JSONL}")
    print(f"-> {OUT_MD}")
    return summary["rc"]


def show():
    if not OUT_MD.exists():
        print("нет сборки — запусти: anatomy.py build")
        return 1
    print(OUT_MD.read_text(encoding="utf-8"))
    return 0


def main():
    ap = argparse.ArgumentParser(description="анатомия Корабля — производная")
    ap.add_argument("cmd", nargs="?", default="build", choices=["build", "show"])
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help="сколько объектов из реестра (pilot по умолчанию 10)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "show":
        return show()
    return build(dry_run=a.dry_run, limit=a.limit)


if __name__ == "__main__":
    raise SystemExit(main())

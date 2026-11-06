#!/usr/bin/env python3
"""build-decide-index — единый индекс решений и ролей (машина, не память).

Причина (слово владельца 2026-11-06 «Делать» на единый реестр ролей): решения и
ответственность записаны в разных местах, и ничто не заставляет прочесть их перед
вопросом владельцу. Поэтому агент спрашивает решённое.

Что делает:
  - собирает решения из волта (реестр решений, журналы сессий, аудиты);
  - собирает роли из реестра отправителей и агентских файлов;
  - пишет один машинный индекс + короткий дайджест для чтения человеком;
  - пишет дату сборки: устаревший индекс виден как устаревший.

Использование:
  build-decide-index.py            # сборка (по умолчанию — всё)
  build-decide-index.py --digest   # только дайджест (короткий вид)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time

VAULT = os.environ.get("OPENCODE_VAULT",
                       os.path.expanduser("~/Projects/OpenCode-Vault"))
OUT_DIR = os.path.expanduser("~/.local/state/decide-index")
OUT_JSON = os.path.join(OUT_DIR, "index.json")
OUT_DIGEST = os.path.join(OUT_DIR, "digest.md")

SOURCES = [
    ("decisions", os.path.join(VAULT, "01-Policies", "decisions-registry.md")),
    ("registry", os.path.join(VAULT, "docs", "org",
                              "ship-representative-sender-registry.md")),
    ("session-log", os.path.join(VAULT, "04-Memory", "session-log")),
    ("audits", os.path.join(VAULT, "06-Audits")),
    ("peer-registry", os.path.join(VAULT, "04-Memory", "peer-registry.md")),
]
MAX_DIGEST_LINES = 40


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _walk_md(root: str) -> list[str]:
    out: list[str] = []
    for base, _dirs, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(".md"):
                out.append(os.path.join(base, name))
    return sorted(out)


def _decisions_from_text(text: str, where: str) -> list[dict]:
    """Канонный формат реестра: '- **Р-NNN (дата)** — решение. Провенанс: ...'."""
    found: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        m = re.search(r"\*\*Р-(\d+)\s*\(([\d\-]+)\)\*\*\s*—\s*(.+)$", s)
        if m:
            what = m.group(3)
            prov = what.find("Провенанс:")
            found.append({"kind": "decision", "id": "Р-" + m.group(1),
                          "date": m.group(2),
                          "what": (what[:prov] if prov > 0 else what)[:240],
                          "where": where})
            continue
        head = re.search(r"^#{1,3}\s*(.+)$", s)
        if head and where.endswith("session-log"):
            continue
        if "РЕШЕНО" in s or "решено владельцем" in s.lower():
            found.append({"kind": "resolved", "id": "", "what": s[:240],
                          "where": where})
    return found


def _roles_from_registry(text: str) -> list[dict]:
    roles: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("| `") and "|" in s[3:]:
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) >= 3 and "профиль-носитель" not in cells[0].lower():
                roles.append({"actor": cells[0].strip("`"), "zone": cells[1],
                              "may": cells[2]})
    return roles


def build() -> dict:
    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
    index: dict = {"built_utc": now, "vault": VAULT, "decisions": [],
                   "roles": [], "sources": [], "signals": [],
                  "signals_resolved_by_decision": []}
    for kind, path in SOURCES:
        if not os.path.exists(path):
            index["sources"].append({"path": path, "status": "missing"})
            continue
        if os.path.isdir(path):
            files = _walk_md(path)
        else:
            files = [path]
        count = 0
        for fp in files:
            text = _read(fp)
            rel = os.path.relpath(fp, VAULT)
            if kind in ("decisions", "session-log", "audits"):
                for item in _decisions_from_text(text, rel):
                    index["decisions"].append(item)
                    count += 1
            if kind == "registry":
                for role in _roles_from_registry(text):
                    index["roles"].append(role)
                    count += 1
        index["sources"].append({"path": path, "status": "read",
                                 "md_files": len(files), "records": count})
    # Перекрёстная сверка: сигнал Следопыта против решений канона
    index["signals"] = _signals_from_follower()
    resolved = _decision_ids(index["decisions"])
    resolved.update({k: v for k, v in _archived_ids().items() if k})
    for sig in index["signals"]:
        owner_dec = resolved.get(sig["id"])
        if owner_dec:
            index["signals_resolved_by_decision"].append(
                {"id": sig["id"], "what": sig["what"], "decision": owner_dec})
    os.makedirs(OUT_DIR, mode=0o700, exist_ok=True)
    fd = os.open(OUT_JSON, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    _write_digest(index)
    return index


def _write_digest(index: dict) -> None:
    lines = ["# Дайджест решений и ролей — читать перед любым вопросом владельцу",
             "",
             f"собрано: {index['built_utc']} · решений: {len(index['decisions'])} · "
             f"ролей: {len(index['roles'])}",
             "правило: если ответ здесь есть — вопроса владельцу НЕТ.",
             "", "## Роли (кто что может от имени Maya)"]
    for role in index["roles"][:12]:
        lines.append(f"- {role['actor']} → {role['zone']}")
    lines += ["", "## Решения (последние 12 по номеру)"]
    numbered = sorted((d for d in index["decisions"] if d["id"]),
                      key=lambda d: int(d["id"].split("-")[1]), reverse=True)
    for item in numbered[:12]:
        lines.append(f"- {item['id']} ({item.get('date','?')}): {item['what']}")
    for item in [d for d in index["decisions"] if not d["id"]][:6]:
        lines.append(f"- без номера: {item['what']}")
    lines += ["", f"источники: "
              + ", ".join(f"{s['path']}({s.get('records', 0)})"
                          for s in index["sources"] if s["status"] == "read")]
    fd = os.open(OUT_DIGEST, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


FOLLOWER = os.path.join(os.path.expanduser("~/dotfiles"),
                        "tools", "follower", "follower.py")


def _signals_from_follower() -> list[dict]:
    """Сигналы Следопыта: id + текст. Нужны, чтобы связать очередь и решения."""
    import subprocess
    out: list[dict] = []
    try:
        res = subprocess.run(["python3", FOLLOWER], capture_output=True,
                             text=True, timeout=180)
    except Exception:  # noqa: BLE001 — следопыт недоступен = нет сигналов
        return out
    in_signals = False
    for line in (res.stdout or "").splitlines():
        s = line.strip()
        if s.startswith("■ СИГНАЛЫ"):
            in_signals = True
            continue
        if in_signals and s.startswith("⚠"):
            body = s[1:].strip()
            sid = body.split(":")[0].strip()
            out.append({"id": sid, "what": body})
        elif in_signals and s.startswith("■"):
            break
    return out


ARCHIVE = os.path.expanduser("~/.local/state/portal-tg/owner-decisions.json")


def _archived_ids() -> dict[str, str]:
    """Закрытые пункты очереди владельца -> решение, которым закрыты."""
    out: dict[str, str] = {}
    try:
        with open(ARCHIVE, encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("archived", []):
            ref = item.get("decision_ref", "")
            m = re.search(r"Р-\d+", ref)
            out[item.get("id", "")] = m.group(0) if m else item.get("status", "")
    except Exception:  # noqa: BLE001 — нет архива = пусто
        pass
    return out


def _decision_ids(decisions: list[dict]) -> dict[str, str]:
    """id задачи -> решение, в тексте которого он упомянут."""
    mapping: dict[str, str] = {}
    for d in decisions:
        text = d.get("what", "")
        for tid in re.findall(r"\b([QT]-\d{3})\b", text):
            mapping.setdefault(tid, d["id"] or "без номера")
    return mapping


def main(argv: list[str]) -> int:
    if argv and argv[0] not in ("--digest", "-h", "--help"):
        print(__doc__)
        return 0
    index = build()
    print(f"decide-index: собрано {index['built_utc']} · решений "
          f"{len(index['decisions'])} · ролей {len(index['roles'])} · "
          f"сигналов {len(index['signals'])} · "
          f"сигналов закрыты решением "
          f"{len(index['signals_resolved_by_decision'])}")
    for row in index["signals_resolved_by_decision"]:
        print(f"  РАСХОЖДЕНИЕ: {row['id']} числится сигналом, но закрыт "
              f"решением {row['decision']}")
    for s in index["sources"]:
        print(f"  {s['status']}: {s['path']} "
              f"(files={s.get('md_files', 0)}, records={s.get('records', 0)})")
    print(f"дайджест: {OUT_DIGEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

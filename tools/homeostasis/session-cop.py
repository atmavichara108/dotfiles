#!/usr/bin/env python3
"""session-cop — сверка peer-registry с живой реальностью (Р-031).

Для каждой строки реестра сессий проверяет по API:
  1. сессия жива (GET /api/session/<id> отвечает 200);
  2. её проект резолвится в каталог (GET /api/project → canonical);
  3. в ЭТОМ каталоге есть агентский файл .opencode/agent/<агент>.md
     (если агент указан в реестре).
Расхождение = инцидент класса «сессия не там» (факт vs реестр) в
~/.local/state/opencode/cop/incidents.jsonl + полный отчёт в report.tsv.

«Реестр врёт» — как было с сессией Служителя (проект dotfiles вместо
волта) — именно то, что ловит коп.

Запуск: python3 session-cop.py [--json] — read-only, отчёто-инструмент.
"""
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request

REGISTRY = os.path.expanduser(
    "~/Projects/OpenCode-Vault/04-Memory/peer-registry.md")
STATE_DIR = os.path.expanduser("~/.local/state/opencode/cop")
INCIDENTS_FILE = os.path.join(STATE_DIR, "incidents.jsonl")
REPORT_FILE = os.path.join(STATE_DIR, "report.tsv")
ENDPOINT = os.environ.get("OPENCODE_ENDPOINT", "http://127.0.0.1:49374")
SERVICE_JSON = os.path.expanduser("~/.config/opencode/service.json")


def auth_headers():
    try:
        tok = json.load(open(SERVICE_JSON, encoding="utf-8")).get("password", "")
    except Exception:  # noqa: BLE001
        return {}
    return {"Authorization":
            "Basic " + base64.b64encode(f"opencode:{tok}".encode()).decode()}


def api_get(path):
    req = urllib.request.Request(ENDPOINT + path, headers=auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001
        return None, str(e)


def registry_rows():
    """Мини-парсер таблицы реестра: (ses, агент, каталог, роль)."""
    rows = []
    if not os.path.exists(REGISTRY):
        return rows
    for line in open(REGISTRY, encoding="utf-8"):
        if "ses_" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        m = re.search(r"ses_[A-Za-z0-9]+", line)
        if not m:
            continue
        sid = m.group(0)
        agent = (cells[2] if len(cells) > 2 else "").replace("**", "").strip()
        home = cells[3] if len(cells) > 3 else ""
        for c in cells:
            c2 = c.replace("**", "").strip()
            if c2.startswith("~") or c2.startswith("/"):
                home = c2
                break
        if agent.startswith("ses_") or not agent or agent == "—":
            agent = ""
        rows.append((sid, agent, home))
    return rows


def projects_index():
    _, d = api_get("/api/project")
    if not d:
        return {}
    d = d.get("data", d) if isinstance(d, dict) else d
    return {p.get("id"): p.get("canonical") for p in d if isinstance(p, dict)}


def main():
    rows = registry_rows()
    idx = projects_index()
    report, divergences = [], []
    for sid, agent, home in rows:
        code, d = api_get(f"/api/session/{sid}")
        d = d.get("data", d) if isinstance(d, dict) else d
        if code == 404 or d is None:
            report.append((sid, agent, home, "НЕ ЖИВА (404/нет ответа)",
                           "исторический след — закрытие за владельцем"))
            divergences.append({"ts": int(_now()), "class": "session-not-alive",
                                "sid": sid, "registry_agent": agent,
                                "registry_home": home})
            continue
        pid = d.get("projectID", "")
        canonical = idx.get(pid)
        agent_norm = agent.replace(" ", "-").replace(".", "-").lower()
        agent_file = os.path.expanduser(
            os.path.join(canonical or "", ".opencode/agent",
                         f"{agent_norm}.md")) if agent else ""
        if agent and canonical and not os.path.exists(agent_file):
            note = f"агент {agent} не резолвится в {canonical}"
            report.append((sid, agent, home, canonical or pid, note))
            divergences.append({"ts": int(_now()), "class": "agent-not-resolvable",
                                "sid": sid, "agent": agent,
                                "project": canonical or pid,
                                "file": agent_file})
        elif home and canonical and not canonical.startswith(home.rstrip("/")) \
                and not home.startswith("~"):
            note = f"каталог {canonical} != реестровый {home}"
            report.append((sid, agent, home, canonical, note))
            divergences.append({"ts": int(_now()), "class": "dir-mismatch",
                                "sid": sid, "registry_home": home,
                                "fact": canonical})
        else:
            report.append((sid, agent, home, canonical or pid, "ок"))

    # --- Оси дрейфа (знаки канала): канал + claims + имена ---
    divergences += drift.axes((1, 2, 3))

    os.makedirs(STATE_DIR, exist_ok=True)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("sid\tagent\thome_реестр\tfact\tnote\n")
        for r in report:
            f.write("\t".join(str(x) for x in r) + "\n")
    for dv in divergences:
        with open(INCIDENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(dv, ensure_ascii=False) + "\n")
    print(f"session-cop: строк реестра {len(rows)}, расхождений "
          f"{len(divergences)} (отчёт: {REPORT_FILE})")
    return 1 if divergences else 0


def _now():
    import time
    return time.time()


# --- Оси дрейфа — общий модуль (мандат sign-rules-to-infra) ---------------
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import drift  # noqa: E402

def registry_ids():
    ids = set()
    if os.path.exists(REGISTRY):
        for line in open(REGISTRY, encoding="utf-8"):
            for m in re.finditer(r"ses_[A-Za-z0-9]+", line):
                ids.add(m.group(0))
    return ids


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""selftest для pin-check (BF-20261119-05).

Проверяет ровно то, ради чего инструмент написан:
  1. пин читается из frontmatter агента; шаблон и агент без пина — не пин;
  2. пин вне каталога помечается (MISSING_MODEL / MISSING_PROVIDER / MALFORMED);
  3. CLI: битый пин → exit 1 (гейт блокирует коммит), хорошие пины → exit 0;
  4. offline-режим (models.dev) — advisory: warns, но не блокирует;
  5. PIN_OK=1 — осознанный обход;
  6. отчёт пишется (меты-only, без секретов).

Запуск: python3 tools/model-watch/pin-check-selftest.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN_CHECK = HERE / "pin-check.py"

PASSED = 0
FAILED: list[str] = []


def ok(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok   {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  FAIL {name} — {detail}")


def load_module():
    spec = importlib.util.spec_from_file_location("pin_check", PIN_CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def agent_md(pin: str | None, extra: str = "") -> str:
    fm = f"model: {pin}\n" if pin else ""
    return (f"---\ndescription: тестовый агент\n{fm}---\n\n# Тест\n{extra}\n")


def main() -> int:
    mod = load_module()
    tmp = Path(tempfile.mkdtemp(prefix="pin-check-selftest-"))

    # --- 1. разбор пина -----------------------------------------------------
    ok("pin: обычный пин читается",
       mod.parse_pin(agent_md("nvidia/meta/muse-glimmer-30b")) ==
       "nvidia/meta/muse-glimmer-30b")
    ok("pin: агент без пина → None", mod.parse_pin(agent_md(None)) is None)
    ok("pin: шаблон {{МОДЕЛЬ}} не пин",
       mod.parse_pin(agent_md("{{МОДЕЛЬ}}")) is None)
    ok("pin: кавычки снимаются",
       mod.parse_pin(agent_md('"nvidia/meta/muse-glimmer-30b"')) ==
       "nvidia/meta/muse-glimmer-30b")
    ok("split: provider/model",
       mod.split_pin("vercel/recursive/flint-v1.0") ==
       ("vercel", "recursive/flint-v1.0"))
    ok("split: без слэша → None", mod.split_pin("muse-glimmer-30b") is None)

    # --- 2. сбор пинов и вердикты -----------------------------------------
    agents = tmp / "agents"
    agents.mkdir()
    (agents / "good.md").write_text(agent_md("nvidia/meta/muse-glimmer-30b"),
                                    encoding="utf-8")
    (agents / "bad-model.md").write_text(
        agent_md("nvidia/moonshotai/kimi-k2.6"), encoding="utf-8")
    (agents / "bad-provider.md").write_text(
        agent_md("nosuchprov/whatever"), encoding="utf-8")
    (agents / "template.md").write_text(agent_md("{{МОДЕЛЬ}}"), encoding="utf-8")
    (agents / "nopin.md").write_text(agent_md(None), encoding="utf-8")

    pins = mod.pins_from_dir(agents)
    names = {a for a, _ in pins}
    ok("сбор: только агенты с пином",
       names == {"good", "bad-model", "bad-provider"}, f"получили {names}")

    catalog = {("nvidia", "meta/muse-glimmer-30b")}
    providers = {"nvidia"}
    findings = mod.check(pins, catalog, providers)
    by_agent = {f["agent"]: f["reason"] for f in findings}
    ok("вердикт: хороший пин без замечаний", "good" not in by_agent, str(by_agent))
    ok("вердикт: модели нет в каталоге → MISSING_MODEL",
       by_agent.get("bad-model") == "MISSING_MODEL", str(by_agent))
    ok("вердикт: провайдера нет → MISSING_PROVIDER",
       by_agent.get("bad-provider") == "MISSING_PROVIDER", str(by_agent))

    # --- 3. CLI: битый пин блокирует --------------------------------------
    catalog_file = tmp / "catalog.json"
    catalog_file.write_text(json.dumps([
        {"providerID": "nvidia", "modelID": "meta/muse-glimmer-30b"}]),
        encoding="utf-8")
    report = tmp / "report.json"
    env = dict(os.environ)
    env["PIN_CHECK_REPORT"] = str(report)

    def run(args: list[str], extra_env: dict | None = None) -> subprocess.CompletedProcess:
        e = dict(env)
        e.update(extra_env or {})
        return subprocess.run([sys.executable, str(PIN_CHECK), *args],
                              capture_output=True, text=True, env=e, timeout=60)

    rc = run(["--agents-dir", str(agents), "--catalog-file", str(catalog_file)])
    ok("CLI: битый пин → exit 1", rc.returncode == 1, f"rc={rc.returncode} {rc.stdout}")
    ok("CLI: в выводе видны имена агентов",
       "bad-model" in rc.stdout and "bad-provider" in rc.stdout, rc.stdout[:300])
    ok("CLI: отчёт записан", report.exists(), str(report))
    if report.exists():
        data = json.loads(report.read_text(encoding="utf-8"))
        ok("отчёт: status=FAIL и есть находки",
           data.get("status") == "FAIL" and data.get("pins_bad") == 2, json.dumps(data)[:300])
        ok("отчёт: без секретов/путей-в-куках",
           "password" not in json.dumps(data).lower(), "")

    good_only = tmp / "good-only"
    good_only.mkdir()
    (good_only / "good.md").write_text(agent_md("nvidia/meta/muse-glimmer-30b"),
                                       encoding="utf-8")
    rc = run(["--agents-dir", str(good_only), "--catalog-file", str(catalog_file)])
    ok("CLI: хорошие пины → exit 0", rc.returncode == 0, f"rc={rc.returncode} {rc.stdout}")

    rc = run(["--agents-dir", str(agents), "--catalog-file", str(catalog_file)],
             {"PIN_OK": "1"})
    ok("CLI: PIN_OK=1 → обход, exit 0", rc.returncode == 0, f"rc={rc.returncode}")

    # --- 4. offline-режим (models.dev) — advisory --------------------------
    snapshot = tmp / "snapshot.json"
    snapshot.write_text(json.dumps({"providers": {
        "nvidia": {"models": {"meta/muse-glimmer-30b": {}}},
    }}), encoding="utf-8")
    rc = run(["--agents-dir", str(agents), "--offline", "--snapshot", str(snapshot)])
    ok("CLI: offline → не блокирует (exit 0)", rc.returncode == 0,
       f"rc={rc.returncode} {rc.stdout}")
    ok("CLI: offline → предупреждение о битом пине",
       "bad-model" in rc.stdout and "WARN" in rc.stdout, rc.stdout[:300])

    # --- 5. JSON-вывод ------------------------------------------------------
    rc = run(["--agents-dir", str(agents), "--catalog-file", str(catalog_file),
              "--json"])
    try:
        data = json.loads(rc.stdout)
        json_ok = (data.get("status") == "FAIL" and
                   len(data.get("new_findings", [])) == 2 and
                   data.get("known_findings") == [])
    except json.JSONDecodeError as exc:
        json_ok = False
        data = {"err": str(exc)}
    ok("CLI: --json отдаёт валидный JSON с находками", json_ok, json.dumps(data)[:300])

    # --- 6. недоступный живой каталог → PASS с предупреждением ------------
    rc = run(["--agents-dir", str(agents)], {"OPENCODE_ENDPOINT": "http://127.0.0.1:1"})
    ok("CLI: сервер мёртв → exit 0 + WARN (не блокируем флот)",
       rc.returncode == 0 and "WARN" in rc.stdout, f"rc={rc.returncode} {rc.stdout[:200]}")

    # --- 7. diff-гейт: базовая линия HEAD ---------------------------------
    repo = tmp / "repo"
    (repo / ".opencode" / "agent").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=60)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True,
                   timeout=60)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True,
                   timeout=60)
    old = repo / ".opencode" / "agent" / "old.md"
    old.write_text(agent_md("nvidia/moonshotai/kimi-k2.6"), encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, timeout=60)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "base"], check=True,
                   timeout=60)
    # staged: старый битый пин остался + появился новый битый пин
    (repo / ".opencode" / "agent" / "new.md").write_text(
        agent_md("opencode/muse-spark-1.3-contributor-free"), encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, timeout=60)

    rc = run(["--staged", "--repo", str(repo), "--catalog-file", str(catalog_file)])
    ok("diff-гейт: новый битый пин → exit 1", rc.returncode == 1,
       f"rc={rc.returncode} {rc.stdout[:300]}")
    ok("diff-гейт: старый битый пин помечен как ⚠️, а не ❌",
       "⚠️  old:" in rc.stdout and "❌ old:" not in rc.stdout, rc.stdout[:300])

    # staged без новых битых пинов (только давно битый) → не блокирует
    subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached",
                    ".opencode/agent/new.md"], check=True, timeout=60)
    (repo / ".opencode" / "agent" / "new.md").unlink()
    rc = run(["--staged", "--repo", str(repo), "--catalog-file", str(catalog_file)])
    ok("diff-гейт: только старый битый пин → exit 0 (флот не встаёт)",
       rc.returncode == 0, f"rc={rc.returncode} {rc.stdout[:300]}")

    # --strict: любой битый пин → FAIL
    rc = run(["--staged", "--strict", "--repo", str(repo),
              "--catalog-file", str(catalog_file)])
    ok("diff-гейт: --strict → exit 1 даже по старому битому пину",
       rc.returncode == 1, f"rc={rc.returncode} {rc.stdout[:200]}")

    print(f"\nPIN-CHECK SELFTEST: {PASSED} passed, {len(FAILED)} failed")
    for item in FAILED:
        print(f"  ! {item}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())

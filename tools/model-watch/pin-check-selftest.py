#!/usr/bin/env python3
"""selftest для pin-check (BF-20261119-05, BF-20261120-01).

Проверяет ровно то, ради чего инструмент написан:
  1. пин читается из frontmatter агента; шаблон и агент без пина — не пин;
  2. пин вне каталога помечается (MISSING_MODEL / MISSING_PROVIDER / MALFORMED);
  3. CLI: битый пин → exit 1 (гейт блокирует коммит), хорошие пины → exit 0;
  4. offline-режим (models.dev) — advisory: warns, но не блокирует;
  5. PIN_OK=1 — осознанный обход;
  6. отчёт пишется (меты-only, без секретов);
  7. ИСТОЧНИК 2 (провайдерный список на нашем ключе): пин есть в каталоге
     OpenCode, но нет у провайдера → MISSING_AT_PROVIDER (exit 1);
  8. провайдер недоступен (нет ключа) → WARN, не FAIL (гейт не встаёт);
  9. алиас шлюза: живая чат-проба с tools; 200 → живой, 404/410 → FAIL,
     «не удалось проверить» → ALIAS_NOT_PROBED (WARN);
 10. факт по Р-109: модель проверяющего в каналах алиаса → предупреждение
     (не блокировка).

Сеть в selftest не используется: провайдер и шлюз — локальная фикстура
(мини-сервер на 127.0.0.1). Базовые тесты идут с --no-provider-check, чтобы
не зависеть от провайдеров.

Запуск: python3 tools/model-watch/pin-check-selftest.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
    (agents / "malformed.md").write_text(agent_md("notaprovider-model"), encoding="utf-8")

    pins = mod.pins_from_dir(agents)
    names = {a for a, _ in pins}
    ok("сбор: только агенты с пином",
       names == {"good", "bad-model", "bad-provider", "malformed"}, f"получили {names}")

    catalog = {("nvidia", "meta/muse-glimmer-30b")}
    providers = {"nvidia"}
    findings = mod.check(pins, catalog, providers)
    by_agent = {f["agent"]: f["reason"] for f in findings}
    ok("вердикт: хороший пин без замечаний", "good" not in by_agent, str(by_agent))
    ok("вердикт: модели нет в каталоге → MISSING_MODEL",
       by_agent.get("bad-model") == "MISSING_MODEL", str(by_agent))
    ok("вердикт: провайдера нет → MISSING_PROVIDER",
       by_agent.get("bad-provider") == "MISSING_PROVIDER", str(by_agent))
    ok("вердикт: неразбираемый пин → MALFORMED",
       by_agent.get("malformed") == "MALFORMED", str(by_agent))
    ok("вердикт: is_pin_broken совпадает с вердиктом check()",
       mod.is_pin_broken("nvidia/meta/muse-glimmer-30b", catalog) is False and
       mod.is_pin_broken("nvidia/moonshotai/kimi-k2.6", catalog) is True and
       mod.is_pin_broken("notaprovider-model", catalog) is True, "")

    # --- 3. CLI: битый пин блокирует --------------------------------------
    catalog_file = tmp / "catalog.json"
    catalog_file.write_text(json.dumps([
        {"providerID": "nvidia", "modelID": "meta/muse-glimmer-30b"}]),
        encoding="utf-8")
    report = tmp / "report.json"
    env = dict(os.environ)
    env["PIN_CHECK_REPORT"] = str(report)

    def run(args: list[str], extra_env: dict | None = None,
            provider_check: bool = False) -> subprocess.CompletedProcess:
        e = dict(env)
        e.update(extra_env or {})
        # Базовые тесты — без источника 2: сеть провайдеров в selftest не нужна.
        if not provider_check:
            args = ["--no-provider-check"] + args
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
           data.get("status") == "FAIL" and data.get("pins_bad") == 3, json.dumps(data)[:300])
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
                   len(data.get("new_findings", [])) == 3 and
                   data.get("known_findings") == [])
    except json.JSONDecodeError as exc:
        json_ok = False
        data = {"err": str(exc)}
    ok("CLI: --json отдаёт валидный JSON с находками", json_ok, json.dumps(data)[:300])

    # --- 5b. пустой каталог → WARN и пропуск (не блокируем флот) -----------
    empty_catalog = tmp / "empty-catalog.json"
    empty_catalog.write_text("[]", encoding="utf-8")
    rc = run(["--agents-dir", str(agents), "--catalog-file", str(empty_catalog)])
    ok("CLI: пустой каталог → exit 0 + WARN",
       rc.returncode == 0 and "WARN" in rc.stdout, f"rc={rc.returncode} {rc.stdout[:200]}")

    # --- 5c. битая структура снапшота → явная ошибка, не тихая --------------
    broken_snapshot = tmp / "broken-snapshot.json"
    broken_snapshot.write_text(json.dumps({"providers": {"nvidia": "строка"}}),
                               encoding="utf-8")
    rc = run(["--agents-dir", str(agents), "--offline",
              "--snapshot", str(broken_snapshot)])
    ok("CLI: битый снапшот → exit 0 + WARN (ошибка не проглатывается молча)",
       rc.returncode == 0 and "WARN" in rc.stdout, f"rc={rc.returncode} {rc.stdout[:200]}")
    ok("CLI: битый снапшот — в сообщении видна причина",
       "провайдер" in rc.stdout or "не объект" in rc.stdout, rc.stdout[:300])

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

    # --- 8. ИСТОЧНИК 2: провайдерный список + алиасы шлюза (фикстура) ------
    class FixtureHandler(BaseHTTPRequestHandler):
        """Мини-шлюз: /models — список моделей, /chat/completions — по alias."""

        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.endswith("/models"):
                body = json.dumps(
                    {"data": [{"id": m} for m in self.server.models]}).encode()
                self.send_response(200)
            else:
                body = b"{}"
                self.send_response(404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                payload = {}
            model = payload.get("model", "")
            status = self.server.alias_status.get(model, 200)
            body = json.dumps({"model": model,
                               "choices": [{"message": {"content": "ok"}}]}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    server.models = ["good/model", "free-code", "gone-alias", "flaky-alias",
                      "cached-alias"]
    server.alias_status = {"free-code": 200, "gone-alias": 404,
                            "flaky-alias": 500, "cached-alias": 200}
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/v1"

    # Второй фикстур: провайдер, который отдаёт ПУСТОЙ список моделей.
    empty_server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
    empty_server.models = []
    empty_server.alias_status = {}
    threading.Thread(target=empty_server.serve_forever, daemon=True).start()
    empty_base = f"http://127.0.0.1:{empty_server.server_address[1]}/v1"

    endpoints = tmp / "endpoints.json"
    endpoints.write_text(json.dumps({
        "fakeprov": {"endpoint": base, "env": "PIN_CHECK_TEST_KEY"},
        "nokeyprov": {"endpoint": base, "env": "PIN_CHECK_ABSENT_KEY"},
        "emptyprov": {"endpoint": empty_base, "env": "PIN_CHECK_TEST_KEY"},
    }), encoding="utf-8")

    catalog2 = tmp / "catalog2.json"
    catalog2.write_text(json.dumps([
        {"providerID": "fakeprov", "modelID": "good/model"},
        {"providerID": "fakeprov", "modelID": "missing/model"},
        {"providerID": "nokeyprov", "modelID": "anything"},
        {"providerID": "emptyprov", "modelID": "whatever"},
        {"providerID": "newapi", "modelID": "free-code"},
        {"providerID": "newapi", "modelID": "gone-alias"},
        {"providerID": "newapi", "modelID": "flaky-alias"},
        {"providerID": "newapi", "modelID": "cached-alias"},
    ]), encoding="utf-8")

    env2 = {"PIN_CHECK_TEST_KEY": "test-key", "NEWAPI_API_KEY": "test-key",
            "PIN_CHECK_CACHE": str(tmp / "cache.json")}
    common2 = ["--catalog-file", str(catalog2), "--provider-endpoints",
               str(endpoints), "--gateway-endpoint", base, "--no-alias-cache"]

    prov_good = tmp / "prov-good"
    prov_good.mkdir()
    (prov_good / "good.md").write_text(
        agent_md("fakeprov/good/model"), encoding="utf-8")
    rc = run(["--agents-dir", str(prov_good)] + common2, env2,
             provider_check=True)
    ok("источник 2: модель есть у провайдера → exit 0",
       rc.returncode == 0, f"rc={rc.returncode} {rc.stdout[:300]}")

    prov_missing = tmp / "prov-missing"
    prov_missing.mkdir()
    (prov_missing / "missing.md").write_text(
        agent_md("fakeprov/missing/model"), encoding="utf-8")
    rc = run(["--agents-dir", str(prov_missing)] + common2, env2,
             provider_check=True)
    ok("источник 2: модели нет у провайдера → MISSING_AT_PROVIDER, exit 1",
       rc.returncode == 1 and "MISSING_AT_PROVIDER" in rc.stdout,
       f"rc={rc.returncode} {rc.stdout[:300]}")

    empty_agents = tmp / "empty-agents"
    empty_agents.mkdir()
    (empty_agents / "empty.md").write_text(
        agent_md("emptyprov/whatever"), encoding="utf-8")
    rc = run(["--agents-dir", str(empty_agents)] + common2, env2,
             provider_check=True)
    ok("источник 2: пустой список моделей → WARN (не FAIL), exit 0",
       rc.returncode == 0 and "UNPROBEABLE" in rc.stdout,
       f"rc={rc.returncode} {rc.stdout[:300]}")

    nokey_agents = tmp / "nokey-agents"
    nokey_agents.mkdir()
    (nokey_agents / "nokey.md").write_text(
        agent_md("nokeyprov/anything"), encoding="utf-8")
    rc = run(["--agents-dir", str(nokey_agents)] + common2, env2,
             provider_check=True)
    ok("источник 2: ключа нет → WARN, не FAIL (exit 0)",
       rc.returncode == 0 and "UNPROBEABLE" in rc.stdout,
       f"rc={rc.returncode} {rc.stdout[:300]}")

    alias_agents = tmp / "alias-agents"
    alias_agents.mkdir()
    (alias_agents / "ok.md").write_text(
        agent_md("newapi/free-code"), encoding="utf-8")
    rc = run(["--agents-dir", str(alias_agents)] + common2, env2,
             provider_check=True)
    ok("алиас: живая проба 200 → exit 0",
       rc.returncode == 0, f"rc={rc.returncode} {rc.stdout[:300]}")

    gone_agents = tmp / "gone-agents"
    gone_agents.mkdir()
    (gone_agents / "gone.md").write_text(
        agent_md("newapi/gone-alias"), encoding="utf-8")
    rc = run(["--agents-dir", str(gone_agents)] + common2, env2,
             provider_check=True)
    ok("алиас: проба 404 → провайдер не отдаёт → exit 1",
       rc.returncode == 1 and "MISSING_AT_PROVIDER" in rc.stdout,
       f"rc={rc.returncode} {rc.stdout[:300]}")

    flaky_agents = tmp / "flaky-agents"
    flaky_agents.mkdir()
    (flaky_agents / "flaky.md").write_text(
        agent_md("newapi/flaky-alias"), encoding="utf-8")
    rc = run(["--agents-dir", str(flaky_agents)] + common2, env2,
             provider_check=True)
    ok("алиас: проба не дала вердикта → ALIAS_NOT_PROBED + WARN, exit 0",
       rc.returncode == 0 and "ALIAS_NOT_PROBED" in rc.stdout,
       f"rc={rc.returncode} {rc.stdout[:300]}")

    # Кэш живой пробы: успех кэшируется, отказ провайдера — коротким TTL.
    cached_agents = tmp / "cached-agents"
    cached_agents.mkdir()
    (cached_agents / "cached.md").write_text(
        agent_md("newapi/cached-alias"), encoding="utf-8")
    cache_args = [a for a in common2 if a != "--no-alias-cache"]
    rc = run(["--agents-dir", str(cached_agents)] + cache_args, env2,
             provider_check=True)
    ok("кэш: первая проба алиаса успешна → exit 0",
       rc.returncode == 0, f"rc={rc.returncode} {rc.stdout[:300]}")
    server.alias_status["cached-alias"] = 404  # провайдер сломался
    rc = run(["--agents-dir", str(cached_agents)] + cache_args, env2,
             provider_check=True)
    ok("кэш: успех взят из кэша (проба не переспрашивается зря) → exit 0",
       rc.returncode == 0, f"rc={rc.returncode} {rc.stdout[:300]}")
    rc = run(["--agents-dir", str(cached_agents)] + common2, env2,
             provider_check=True)
    ok("кэш: без кэша (--no-alias-cache) отказ провайдера виден сразу → exit 1",
       rc.returncode == 1 and "MISSING_AT_PROVIDER" in rc.stdout,
       f"rc={rc.returncode} {rc.stdout[:300]}")

    # Р-109: модель проверяющего в каналах алиаса → предупреждение, не блокировка
    gwdb = tmp / "gateway.db"
    con = sqlite3.connect(gwdb)
    con.execute("create table abilities (model text, channel_id integer)")
    con.execute("create table channels (id integer, name text, model_mapping text)")
    con.execute("insert into channels values (7, ?, ?)",
                ("nvidia|poolside/laguna-xs-2.1|free-code",
                 json.dumps({"free-code": "poolside/laguna-xs-2.1"})))
    con.execute("insert into abilities values ('free-code', 7)")
    con.commit()
    con.close()
    rc = run(["--agents-dir", str(alias_agents)] + common2,
             {**env2, "GATEWAY_DB": str(gwdb)}, provider_check=True)
    ok("Р-109: модель проверяющего в канале алиаса → предупреждение, не FAIL",
       rc.returncode == 0 and "Р-109" in rc.stdout,
       f"rc={rc.returncode} {rc.stdout[:300]}")

    print(f"\nPIN-CHECK SELFTEST: {PASSED} passed, {len(FAILED)} failed")
    for item in FAILED:
        print(f"  ! {item}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())

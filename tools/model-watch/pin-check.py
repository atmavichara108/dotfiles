#!/usr/bin/env python3
"""pin-check — пин моделей агентов против ЖИВОГО каталога OpenCode.

Дефект, который закрывает (BF-20261119-05): пин модели, которой нет в
каталоге, OpenCode принимает БЕЗ ошибки — POST /api/session/<id>/model
возвращает 204, и на запросе сессия тихо уходит на дефолтную модель агента.
Экземпляр 19.11: verifier с пином nvidia/moonshotai/kimi-k2.6 (модели нет в
каталоге) ушёл на дефолт агента — AMD-ключ с лимитом 1 запрос/сутки.
Второй экземпляр, живой на 19.11: .opencode/agent/sysop.md —
opencode/muse-spark-1.3-contributor-free (в живом каталоге такого id нет).

Каталог — ТОЛЬКО GET /api/model (канон метода): у openai-compatible
провайдеров (nvidia и др.) /api/provider возвращает пустой список, и это НЕ
значит «моделей нет» — ложное срабатывание дороже пропуска.

Источники пинов:
  --agents-dir DIR   каталог агентских .md (по умолчанию — оба слоя dotfiles:
                     .opencode/agent и opencode-global/.config/opencode/agent)
  --staged           читать пины из индекса git: проверяем то, что УЖЕ в
                     коммите (починенный пин проходит гейт тем же коммитом)
  --live-layer       дополнительно проверить живой слой ~/.config/opencode/agent

Diff-гейт (важно): в --staged блокируется только НОВЫЙ битый пин (не битый в
HEAD). Уже сломанный пин — решение по нему ещё не принято — печатается как
⚠️, но не блокирует чужие коммиты: иначе один старый пин встанет весь флот.
--strict отключает это правило (ручная проверка флота: любой битый пин = FAIL).

Каталог:
  по умолчанию — живой: GET {OPENCODE_ENDPOINT}/api/model, токен из
  ~/.config/opencode/service.json (тот же путь, что у wake.py).
  --offline — снапшот models.dev (control-plane/model-catalog.json).
  ВНИМАНИЕ: models.dev ≠ каталог провайдера у OpenCode (напр. flint-v1.0 в
  models.dev нет, а в живом каталоге есть) → в offline-режиме отсутствие пина
  это WARN, а не FAIL (иначе гейт блокирует коммиты из-за чужого источника).

Коды: 0 — все пины в каталоге (или живой каталог недоступен: проверка
      пропущена с явным предупреждением); 1 — пин вне каталога; 2 — ошибка.
Обход (осознанный): PIN_OK=1 — рядом с причиной в сообщении коммита.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINT = os.environ.get("OPENCODE_ENDPOINT", "http://127.0.0.1:49374")
SERVICE_JSON = Path.home() / ".config" / "opencode" / "service.json"
SNAPSHOT = Path(os.environ.get(
    "MODEL_WATCH_SNAPSHOT",
    Path.home() / "Projects" / "OpenCode-Vault" / "control-plane" /
    "model-catalog.json"))
REPORT = Path(os.environ.get(
    "PIN_CHECK_REPORT",
    Path.home() / ".local" / "state" / "opencode" / "model-watch" /
    "pin-report.json"))
LIVE_AGENT_DIR = Path.home() / ".config" / "opencode" / "agent"
REPO = Path(__file__).resolve().parents[2]

DEFAULT_AGENT_DIRS = (
    REPO / ".opencode" / "agent",
    REPO / "opencode-global" / ".config" / "opencode" / "agent",
)

PIN_RE = re.compile(r"^model:\s*(\S+)\s*$", re.M)
TEMPLATE_MARK = ("{", "}", "<", ">")


def die(msg: str, code: int = 2) -> None:
    print(f"pin-check: {msg}", file=sys.stderr)
    sys.exit(code)


def parse_pin(text: str) -> str | None:
    """Пин из frontmatter агента. None — пина нет (агент на дефолте)."""
    m = PIN_RE.search(text)
    if not m:
        return None
    pin = m.group(1).strip().strip('"').strip("'")
    # Шаблоны (subagent-archetype: "{{МОДЕЛЬ}}") — не пин.
    if not pin or any(tok in pin for tok in TEMPLATE_MARK):
        return None
    return pin


def split_pin(pin: str) -> tuple[str, str] | None:
    prov, sep, mid = pin.partition("/")
    if not sep or not prov or not mid:
        return None
    return prov, mid


def pins_from_dir(directory: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        pin = parse_pin(text)
        if pin:
            out.append((path.stem, pin))
    return out


def pins_from_index(repo: Path) -> list[tuple[str, str]]:
    """Пины из индекса git — то, что попадёт в коммит."""
    env = dict(os.environ)
    out: list[tuple[str, str]] = []
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-s", "--", "*/agent/*.md", "*agent/*.md"],
            cwd=repo, env=env, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return out
    if listing.returncode != 0:
        return out
    for line in listing.stdout.splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) < 4:
            continue
        sha, path = parts[1], parts[3]
        blob = subprocess.run(["git", "cat-file", "blob", sha], cwd=repo, env=env,
                              capture_output=True, text=True, timeout=60)
        if blob.returncode != 0:
            continue
        pin = parse_pin(blob.stdout)
        if pin:
            out.append((Path(path).stem, pin))
    return out


def pins_from_ref(ref: str, repo: Path) -> list[tuple[str, str]]:
    """Пины из git-рефа (например HEAD) — базовая линия для diff-гейта."""
    env = dict(os.environ)
    out: list[tuple[str, str]] = []
    try:
        listing = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref], cwd=repo, env=env,
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return out
    if listing.returncode != 0:
        return out
    for path in listing.stdout.splitlines():
        if not re.search(r"(^|/)agent/[^/]+\.md$", path):
            continue
        blob = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=repo, env=env,
                              capture_output=True, text=True, timeout=60)
        if blob.returncode != 0:
            continue
        pin = parse_pin(blob.stdout)
        if pin:
            out.append((Path(path).stem, pin))
    return out


def catalog_live() -> tuple[set[tuple[str, str]], set[str]]:
    """Живой каталог OpenCode: GET /api/model → ((providerID, modelID), ...)."""
    try:
        tok = json.loads(SERVICE_JSON.read_text(encoding="utf-8")).get("password", "")
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"нет токена {SERVICE_JSON}: {exc}") from exc
    headers = {"Authorization": "Basic " + base64.b64encode(
        f"opencode:{tok}".encode()).decode(), "Content-Type": "application/json"}
    req = urllib.request.Request(f"{ENDPOINT}/api/model", headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    data = payload.get("data", payload) if isinstance(payload, dict) else payload
    pairs = set()
    for item in data or []:
        if not isinstance(item, dict):
            continue
        prov, mid = item.get("providerID"), item.get("modelID")
        if prov and mid:
            pairs.add((prov, mid))
    return pairs, {p for p, _ in pairs}


def catalog_offline(path: Path) -> tuple[set[tuple[str, str]], set[str]]:
    """Снапшот models.dev: providers.<id>.models.<modelID>."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    providers = data.get("providers", {})
    pairs = set()
    for prov, block in providers.items():
        for mid in (block or {}).get("models", {}):
            pairs.add((prov, mid))
    return pairs, set(providers)


def collect_pins(args: argparse.Namespace) -> list[tuple[str, str]]:
    pins: list[tuple[str, str]] = []
    if args.staged:
        pins.extend(pins_from_index(Path(args.repo)))
    else:
        for directory in args.agents_dir:
            pins.extend(pins_from_dir(Path(directory)))
    if args.live_layer:
        pins.extend(pins_from_dir(LIVE_AGENT_DIR))
    seen = set()
    unique = []
    for agent, pin in pins:
        key = (agent, pin)
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def check(pins: list[tuple[str, str]], catalog: set[tuple[str, str]],
          providers: set[str]) -> list[dict]:
    findings: list[dict] = []
    for agent, pin in pins:
        parts = split_pin(pin)
        if parts is None:
            findings.append({"agent": agent, "pin": pin, "reason": "MALFORMED"})
            continue
        prov, mid = parts
        if (prov, mid) in catalog:
            continue
        reason = "MISSING_PROVIDER" if prov not in providers else "MISSING_MODEL"
        findings.append({"agent": agent, "pin": pin, "reason": reason})
    return findings


def split_new_findings(findings: list[dict], baseline_broken: set[str]) -> list[dict]:
    """Новые битые пины — те, что не были битыми в базовой линии (HEAD).

    Принцип diff-гейта: уже сломанный пин (решение по нему ещё не принято)
    не должен блокировать чужие коммиты, но обязан оставаться громким.
    Новый битый пин — всегда FAIL.
    """
    return [f for f in findings if f["pin"] not in baseline_broken]


def write_report(source: str, pins: list[tuple[str, str]], findings: list[dict],
                 status: str) -> None:
    try:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({
            "checked_at": int(time.time()),
            "source": source,
            "status": status,
            "pins_total": len(pins),
            "pins_bad": len(findings),
            "findings": findings,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # отчёт — вспомогательный, ошибка записи не должна ломать гейт


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка пинов моделей агентов")
    parser.add_argument("--agents-dir", action="append", default=[],
                        help="каталог агентских .md (можно указать несколько раз)")
    parser.add_argument("--staged", action="store_true",
                        help="читать пины из индекса git (что попадёт в коммит)")
    parser.add_argument("--live-layer", action="store_true",
                        help="дополнительно проверить ~/.config/opencode/agent")
    parser.add_argument("--offline", action="store_true",
                        help="каталог из снапшота models.dev (advisory, не FAIL)")
    parser.add_argument("--catalog-file", default=None,
                        help="файл каталога в формате живого /api/model "
                             "(список {providerID, modelID}) — авторитетный источник")
    parser.add_argument("--snapshot", default=str(SNAPSHOT))
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--baseline", default="HEAD",
                        help="реф для базовой линии (в --staged: что уже в HEAD)")
    parser.add_argument("--strict", action="store_true",
                        help="FAIL по любому битому пину, даже если он был битым "
                             "уже в HEAD (ручная проверка флота)")
    parser.add_argument("--json", action="store_true", help="вывод в JSON")
    parser.add_argument("--quiet", action="store_true", help="только итог")
    args = parser.parse_args(argv)

    if os.environ.get("PIN_OK") == "1":
        print("pin-check: PASS (PIN_OK=1 bypass)")
        return 0

    if not args.agents_dir:
        args.agents_dir = [str(d) for d in DEFAULT_AGENT_DIRS]
    pins = collect_pins(args)
    if not pins:
        print("pin-check: пинов не найдено — проверять нечего")
        write_report("none", pins, [], "EMPTY")
        return 0

    advisory = args.offline
    source = "models.dev-snapshot"
    try:
        if args.catalog_file:
            raw = json.loads(Path(args.catalog_file).read_text(encoding="utf-8"))
            items = raw.get("data", raw) if isinstance(raw, dict) else raw
            catalog = {(i.get("providerID"), i.get("modelID")) for i in items
                       if isinstance(i, dict) and i.get("providerID") and i.get("modelID")}
            providers = {p for p, _ in catalog}
            source = "catalog-file"
        elif args.offline:
            catalog, providers = catalog_offline(Path(args.snapshot))
        else:
            catalog, providers = catalog_live()
            source = "opencode-api:/api/model"
    except (RuntimeError, urllib.error.URLError, OSError, ValueError,
            json.JSONDecodeError) as exc:
        # Живой каталог недоступен — блокировать коммит из-за этого нельзя:
        # молчаливый PASS был бы тем же дефектом, который чиним.
        print(f"pin-check: WARN — каталог недоступен ({exc}); проверка пропущена")
        write_report(source, pins, [], "SKIPPED_NO_CATALOG")
        return 0

    findings = check(pins, catalog, providers)

    # Diff-гейт: в --staged блокируем только НОВЫЕ битые пины; уже сломанный
    # пин (решение ещё не принято) остаётся громким, но не блокирует чужие
    # коммиты — иначе один старый пин встанет весь флот.
    known: list[dict] = []
    new: list[dict] = findings
    if args.staged and not args.strict:
        baseline = pins_from_ref(args.baseline, Path(args.repo))
        baseline_broken = {pin for _, pin in baseline
                           if (split_pin(pin) or ("", "")) not in catalog}
        new = split_new_findings(findings, baseline_broken)
        known = [f for f in findings if f not in new]

    status = "FAIL" if new else ("WARN" if known else "PASS")
    write_report(source, pins, findings, status)

    if args.json:
        print(json.dumps({
            "source": source, "status": status, "pins_total": len(pins),
            "new_findings": new, "known_findings": known},
            ensure_ascii=False, indent=2))
    else:
        for item in new:
            print(f"  ❌ {item['agent']}: {item['pin']} — {item['reason']}")
        for item in known:
            print(f"  ⚠️  {item['agent']}: {item['pin']} — {item['reason']} "
                  f"(бит и до этого коммита — решение по нему не принято)")
        if new:
            print(f"pin-check: FAIL — {len(new)} НОВЫХ битых пин(ов) ({source}); "
                  f"модель вне каталога = тихий фолбэк на дефолт агента")
        elif known:
            print(f"pin-check: WARN — {len(known)} ранее битых пин(ов) "
                  f"(не блокирует), {len(pins)} всего ({source})")
        elif not args.quiet:
            print(f"pin-check: PASS — {len(pins)} пин(ов) в каталоге ({source})")

    if new and advisory:
        # models.dev ≠ каталог провайдера: не блокируем, но говорим громко.
        print("pin-check: WARN (offline-режим: источник advisory, не блокирует)")
        return 0
    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())

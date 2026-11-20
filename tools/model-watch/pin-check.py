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

ДВА источника живости (BF-20261120-01): каталога OpenCode мало — у
openai-compatible провайдеров он статический, и умершие модели в нём остаются
(24 агента стояли на nvidia/deepseek-ai/deepseek-v4.1-flash: в каталоге есть,
у провайдера — 410 Gone).
  Источник 1 — каталог OpenCode (GET /api/model): «пин разрешается в контуре».
  Источник 2 — список моделей провайдера НА НАШЕМ ключе (GET {endpoint}/models):
    «модель реально обслуживается тем ключом, которым мы платим».
Пин жив, только если он есть в обоих. Источник 2 недоступен (нет ключа,
провайдер не отдаёт список, 403) → WARN, не FAIL: гейт не должен вставать из-за
провайдера, который нечем проверить; молчаливый PASS без предупреждения — тот
же дефект.
  Алиасы шлюза (newapi/free-code, newapi/free-general) — особый случай: их
  «провайдер» сам шлюз. Живость алиаса = алиас есть в каталоге шлюза (GET
  {gateway}/v1/models) И проходит живой чат-пробу (с tools). Плюс факт по
  Р-109: если модель проверяющего входит в каналы алиаса — предупреждение
  (не блокировка): исполнитель может сесть на модель проверяющего.
  Ключи: env → vault .env → credential-store OpenCode (auth.json, затем
  opencode.db/credential). Секреты в отчёт не попадают.

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

# --- Источник 2: провайдерный список моделей на нашем ключе -----------------
GATEWAY_PROVIDER_ID = "newapi"          # шлюз-ротатор в контуре OpenCode
PROVIDER_CATALOG = Path(os.environ.get(
    "PIN_CHECK_PROVIDERS",
    Path.home() / "Projects" / "OpenCode-Vault" / "tools" / "key-rotator" /
    "providers.json"))
AUTH_JSON = Path.home() / ".local" / "share" / "opencode" / "auth.json"
CREDENTIAL_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
VAULT_ENV = Path.home() / "Projects" / "OpenCode-Vault" / ".env"
GATEWAY_DB = Path(os.environ.get(
    "GATEWAY_DB", Path.home() / ".local" / "share" / "newapi" / "one-api.db"))
CACHE = Path(os.environ.get(
    "PIN_CHECK_CACHE",
    Path.home() / ".local" / "state" / "opencode" / "model-watch" /
    "pin-cache.json"))
CACHE_TTL_OK = 900   # успешная проба: кэш 15 минут (гейт не тормозит каждый коммит)
CACHE_TTL_BAD = 60   # отказ провайдера (404/410): кэш 1 минута — починка видна сразу

# Каталог провайдеров — из волта; этот встроенный набор нужен, если волт недоступен.
FALLBACK_PROVIDERS = {
    "nvidia": {"endpoint": "https://integrate.api.nvidia.com/v1",
               "env": "NVIDIA_API_KEY", "auth_id": "nvidia"},
    "vercel": {"endpoint": "https://ai-gateway.vercel.sh/v1",
               "env": None, "auth_id": "vercel"},
    "newapi": {"endpoint": "http://localhost:3000/v1",
               "env": "NEWAPI_API_KEY", "auth_id": "newapi"},
}

# Вердикты: блокирующие — против них гейт падает; предупреждения — нет.
BLOCKING_REASONS = {"MISSING_MODEL", "MISSING_PROVIDER", "MISSING_AT_PROVIDER",
                    "MALFORMED"}
WARN_REASONS = {"UNPROBEABLE", "ALIAS_NOT_PROBED"}


DEFAULT_AGENT_DIRS = (
    REPO / ".opencode" / "agent",
    REPO / "opencode-global" / ".config" / "opencode" / "agent",
)

PIN_RE = re.compile(r"^model:\s*(\S+)\s*$", re.M)
TEMPLATE_MARK = ("{", "}", "<", ">")
# Агентский каталог — каталог с именем ровно "agent" (тот же отбор, что и в
# гейте pre-commit: '(^|/)agent/[^/]+\.md$').
AGENT_PATH_RE = re.compile(r"(^|/)agent/[^/]+\.md$")


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
        # Тот же отбор, что и у pins_from_ref и у гейта в pre-commit:
        # агентский каталог — это каталог с именем ровно "agent".
        if not AGENT_PATH_RE.search(path):
            continue
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
        if not AGENT_PATH_RE.search(path):
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
    """Снапшот models.dev: providers.<id>.models.<modelID>.

    Структура проверяется: битый снапшот должен дать явную ошибку, а не молча
    превратиться в «каталог без моделей» (иначе проверка пинов станет
    фиктивно-зелёной или фиктивно-красной).
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("снапшот: ожидался объект JSON")
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        raise ValueError("снапшот: providers — не объект")
    pairs = set()
    for prov, block in providers.items():
        if not isinstance(block, dict):
            raise ValueError(f"снапшот: провайдер {prov} — не объект")
        models = block.get("models", {})
        if not isinstance(models, dict):
            raise ValueError(f"снапшот: models провайдера {prov} — не объект")
        for mid in models:
            pairs.add((prov, mid))
    return pairs, set(providers)


def is_pin_broken(pin: str, catalog: set[tuple[str, str]]) -> bool:
    """Пин не разрешается в каталоге (включая неразбираемый формат)."""
    parts = split_pin(pin)
    if parts is None:
        return True
    return parts not in catalog


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


def write_report(source: str, pins: list[tuple[str, str]], findings: list[dict],
                 status: str, extra: dict | None = None) -> None:
    try:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({
            "checked_at": int(time.time()),
            "source": source,
            "status": status,
            "pins_total": len(pins),
            "pins_bad": len(findings),
            "findings": findings,
            **(extra or {}),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass  # отчёт — вспомогательный, ошибка записи не должна ломать гейт


# ---------------------------------------------------------------------------
# Источник 2: провайдерный список моделей на НАШЕМ ключе + живая проба алиаса
# ---------------------------------------------------------------------------

_PROVIDER_CATALOG_CACHE: dict[str, dict] | None = None


def load_provider_catalog() -> dict[str, dict]:
    """Каталог провайдеров (endpoint + где брать ключ) — из волта, с запасным набором."""
    global _PROVIDER_CATALOG_CACHE
    if _PROVIDER_CATALOG_CACHE is not None:
        return _PROVIDER_CATALOG_CACHE
    catalog: dict[str, dict] = {}
    try:
        raw = json.loads(PROVIDER_CATALOG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    providers = raw.get("providers") if isinstance(raw, dict) else None
    for pid, spec in (providers or {}).items():
        if isinstance(spec, dict) and spec.get("endpoint"):
            catalog[pid] = {
                "endpoint": str(spec["endpoint"]).rstrip("/"),
                "env": spec.get("env"),
                "auth_id": spec.get("auth_id") or pid,
            }
    for pid, spec in FALLBACK_PROVIDERS.items():
        catalog.setdefault(pid, dict(spec))
    _PROVIDER_CATALOG_CACHE = catalog
    return catalog


def provider_spec(provider: str, args: argparse.Namespace | None = None) -> dict | None:
    """Спецификация провайдера: endpoint + env-имя + id в credential-store."""
    overrides = {}
    if args is not None:
        raw = getattr(args, "provider_endpoints", None)
        if raw:
            try:
                overrides = json.loads(Path(raw).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                overrides = {}
    override = overrides.get(provider) if isinstance(overrides, dict) else None
    if isinstance(override, dict) and override.get("endpoint"):
        base = FALLBACK_PROVIDERS.get(provider, {})
        return {
            "endpoint": str(override["endpoint"]).rstrip("/"),
            "env": override.get("env", base.get("env")),
            "auth_id": override.get("auth_id", provider),
        }
    if isinstance(override, str) and override:
        base = FALLBACK_PROVIDERS.get(provider, {})
        return {"endpoint": override.rstrip("/"), "env": base.get("env"),
                "auth_id": provider}
    return load_provider_catalog().get(provider)


def _vault_dotenv() -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        for line in VAULT_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            data[name.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass
    return data


def _credential_from_db(provider: str) -> str | None:
    """Ключ из credential-store OpenCode (opencode.db, таблица credential)."""
    if not CREDENTIAL_DB.exists():
        return None
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{CREDENTIAL_DB}?mode=ro", uri=True, timeout=5)
        try:
            row = con.execute(
                "select value from credential where integration_id=? "
                "and (active is null or active=1) "
                "order by time_updated desc limit 1", (provider,)).fetchone()
        finally:
            con.close()
    except Exception:
        return None
    if not row or not row[0]:
        return None
    raw = row[0]
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return str(raw)
    if isinstance(data, dict):
        for field in ("key", "apiKey", "value", "token"):
            val = data.get(field)
            if isinstance(val, str) and val:
                return val
        return None
    return str(data)


def resolve_provider_key(provider: str, spec: dict | None) -> tuple[str | None, str]:
    """Ключ провайдера: env → vault .env → credential-store OpenCode.

    Возвращает (ключ, источник). Ключ в отчёт не попадает.
    """
    spec = spec or {}
    env_name = spec.get("env")
    if env_name:
        val = os.environ.get(env_name)
        if val:
            return val, f"env:{env_name}"
        val = _vault_dotenv().get(env_name)
        if val:
            return val, "vault:.env"
    auth_id = spec.get("auth_id") or provider
    try:
        auth = json.loads(AUTH_JSON.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        auth = {}
    entry = auth.get(auth_id) if isinstance(auth, dict) else None
    val = None
    if isinstance(entry, dict):
        val = entry.get("key")
    elif isinstance(entry, str):
        val = entry
    if isinstance(val, str) and val:
        return val, "auth.json"
    val = _credential_from_db(provider)
    if val:
        return val, "credential-store:opencode.db"
    return None, "нет ключа"


def normalize_id(model_id: str) -> str:
    return model_id.strip().lower()


def normalized_ids(ids) -> set[str]:
    """Нормализованные id: как есть + без префикса провайдера.

    У nvidia в списке id вида «nvidia/nemotron-…», у openrouter — «meta/…»:
    пин может быть записан с префиксом и без.
    """
    out: set[str] = set()
    for mid in ids:
        if not isinstance(mid, str) or not mid.strip():
            continue
        out.add(normalize_id(mid))
        if "/" in mid:
            out.add(normalize_id(mid.split("/", 1)[1]))
    return out


def fetch_models(endpoint: str, key: str | None, timeout: int = 25
                 ) -> tuple[set[str], str | None]:
    """GET {endpoint}/models → (модели, ошибка|None)."""
    if not key:
        return set(), "нет ключа"
    url = endpoint.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return set(), f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return set(), type(exc).__name__
    except json.JSONDecodeError:
        return set(), "не-JSON"
    data = payload.get("data") if isinstance(payload, dict) else payload
    if isinstance(data, dict):
        data = data.get("models") or []
    ids: set[str] = set()
    for item in data or []:
        if isinstance(item, str):
            ids.add(item)
        elif isinstance(item, dict):
            mid = item.get("id") or item.get("model") or item.get("modelID")
            if isinstance(mid, str) and mid:
                ids.add(mid)
    return ids, None


PROBE_TOOLS = [{"type": "function", "function": {
    "name": "ping",
    "description": "проверка живости алиаса",
    "parameters": {"type": "object", "properties": {}},
}}]


def probe_alias(endpoint: str, key: str, alias: str, timeout: int = 90
                ) -> tuple[str, str | None]:
    """Живая проба алиаса шлюза (с tools).

    ok | provider-error (404/410 — провайдер не отдаёт модель) | unprobeable.
    """
    body = json.dumps({
        "model": alias,
        "messages": [{"role": "user", "content": "say ok"}],
        "max_tokens": 16,
        "tools": PROBE_TOOLS,
    }).encode()
    req = urllib.request.Request(
        endpoint.rstrip("/") + "/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            if resp.status == 200:
                return "ok", None
            return "unprobeable", f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 410):
            return "provider-error", f"HTTP {exc.code}"
        return "unprobeable", f"HTTP {exc.code}"
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return "unprobeable", type(exc).__name__


def cache_read() -> dict:
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def cached_alias(alias: str) -> str | None:
    """Вердикт из кэша, если он не протух.

    TTL зависит от типа вердикта: успех живёт дольше (иначе каждый коммит ждёт
    пробу), отказ провайдера — коротко (иначе починка провайдера не видна
    минутами, и это ровно тот дефект, который кэш не должен прятать).
    """
    entry = cache_read().get(alias)
    if not isinstance(entry, dict):
        return None
    at = entry.get("at")
    status = entry.get("status")
    if not isinstance(at, int) or status not in ("ok", "provider-error",
                                                  "unprobeable"):
        return None
    ttl = CACHE_TTL_OK if status == "ok" else CACHE_TTL_BAD
    if time.time() - at > ttl:
        return None
    return status


def cache_alias(alias: str, status: str) -> None:
    data = cache_read()
    data[alias] = {"at": int(time.time()), "status": status}
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    except OSError:
        pass


def collect_provider_state(pins: list[tuple[str, str]],
                           args: argparse.Namespace
                           ) -> tuple[dict[str, set[str]], dict[str, str]]:
    """Список моделей провайдеров (один запрос на провайдера) + ошибки.

    provider → нормализованные id; provider → текст ошибки (значит UNPROBEABLE).
    """
    state: dict[str, set[str]] = {}
    errors: dict[str, str] = {}
    fixture = None
    if getattr(args, "provider_models_file", None):
        try:
            fixture = json.loads(Path(args.provider_models_file).read_text(
                encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            fixture = None
    wanted: set[str] = set()
    for _, pin in pins:
        parts = split_pin(pin)
        if parts and parts[0] != GATEWAY_PROVIDER_ID:
            wanted.add(parts[0])
    for provider in sorted(wanted):
        if isinstance(fixture, dict) and provider in fixture:
            ids = fixture[provider]
            if isinstance(ids, dict):
                ids = list(ids.keys())
            state[provider] = normalized_ids(ids or [])
            continue
        spec = provider_spec(provider, args)
        if not spec or not spec.get("endpoint"):
            errors[provider] = "нет публичного эндпоинта"
            continue
        key, source = resolve_provider_key(provider, spec)
        if not key:
            errors[provider] = f"нет ключа ({source})"
            continue
        ids, err = fetch_models(spec["endpoint"], key)
        if err:
            errors[provider] = f"список моделей недоступен ({err})"
            continue
        if not ids:
            # Пустой ответ неотличим от сломанного: молчаливый FAIL на весь
            # флот провайдера — тот же дефект, что был с пустым каталогом
            # OpenCode. Явный WARN и пропуск проверки этого провайдера.
            errors[provider] = "пустой список моделей"
            continue
        state[provider] = normalized_ids(ids)
    return state, errors


def checker_models() -> dict[str, str]:
    """Модели проверяющих — из живого слоя (fallback — константы Р-109)."""
    out: dict[str, str] = {}
    for role, fallback in (("reviewer", "poolside/laguna-xs-2.1"),
                           ("verifier", "recursive/flint-v1.0")):
        pin = None
        try:
            pin = parse_pin((LIVE_AGENT_DIR / f"{role}.md").read_text(
                encoding="utf-8", errors="replace"))
        except OSError:
            pin = None
        parts = split_pin(pin) if pin else None
        out[role] = parts[1] if parts else fallback
    return out


def r109_conflicts(aliases: list[str]) -> list[str]:
    """Р-109: модель проверяющего в каналах алиаса (факт, не блокировка)."""
    if not aliases or not GATEWAY_DB.exists():
        return []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{GATEWAY_DB}?mode=ro", uri=True, timeout=5)
        try:
            placeholders = ",".join("?" * len(aliases))
            rows = con.execute(
                "select a.model, c.id, c.name, c.model_mapping from abilities a "
                f"join channels c on c.id = a.channel_id "
                f"where a.model in ({placeholders})", aliases).fetchall()
        finally:
            con.close()
    except Exception:
        return []
    checkers = checker_models()
    warnings: list[str] = []
    for model, cid, cname, mapping in rows:
        try:
            mapping_obj = json.loads(mapping) if mapping else {}
        except (TypeError, json.JSONDecodeError):
            mapping_obj = {}
        served = {normalize_id(v) for v in (mapping_obj or {}).values()}
        for role, cmodel in checkers.items():
            cm = normalize_id(cmodel)
            if cm in served or cm.split("/")[-1] in {s.split("/")[-1] for s in served}:
                warnings.append(
                    f"Р-109: канал {cid} ({cname}) в алиасе {model} отдаёт "
                    f"модель проверяющего {role}: {cmodel}")
    unique: list[str] = []
    for item in warnings:
        if item not in unique:
            unique.append(item)
    return unique


def check_aliases(pins: list[tuple[str, str]], args: argparse.Namespace
                  ) -> tuple[list[dict], list[str]]:
    """Алиасы шлюза: каталог шлюза + живая проба с tools; + факт по Р-109."""
    aliases: list[str] = []
    for _, pin in pins:
        parts = split_pin(pin)
        if parts and parts[0] == GATEWAY_PROVIDER_ID and parts[1] not in aliases:
            aliases.append(parts[1])
    findings: list[dict] = []
    warnings: list[str] = []
    if not aliases:
        return findings, warnings

    spec = provider_spec(GATEWAY_PROVIDER_ID, args) or {}
    endpoint = getattr(args, "gateway_endpoint", None) or spec.get("endpoint") or ""
    endpoint = str(endpoint).rstrip("/")
    key, key_source = resolve_provider_key(GATEWAY_PROVIDER_ID, spec)

    alias_by_agent = {alias: [agent for agent, pin in pins
                              if (parts := split_pin(pin))
                              and parts[0] == GATEWAY_PROVIDER_ID
                              and parts[1] == alias]
                      for alias in aliases}

    if not endpoint:
        for alias, agents in alias_by_agent.items():
            for agent in agents:
                findings.append({"agent": agent, "pin": f"{GATEWAY_PROVIDER_ID}/{alias}",
                                 "reason": "ALIAS_NOT_PROBED",
                                 "detail": "нет эндпоинта шлюза"})
        return findings, warnings

    ids, err = fetch_models(endpoint, key)
    if err:
        for alias, agents in alias_by_agent.items():
            for agent in agents:
                findings.append({"agent": agent, "pin": f"{GATEWAY_PROVIDER_ID}/{alias}",
                                 "reason": "ALIAS_NOT_PROBED",
                                 "detail": f"каталог шлюза недоступен ({err})"})
        return findings, warnings

    served = normalized_ids(ids)
    for alias, agents in alias_by_agent.items():
        if normalize_id(alias) not in served:
            for agent in agents:
                findings.append({"agent": agent, "pin": f"{GATEWAY_PROVIDER_ID}/{alias}",
                                 "reason": "MISSING_AT_PROVIDER",
                                 "detail": "шлюз не отдаёт этот алиас"})

    if not args.no_alias_probe:
        for alias, agents in alias_by_agent.items():
            if normalize_id(alias) not in served:
                continue  # уже зафиксировано как MISSING_AT_PROVIDER
            status = None
            detail = None
            if not args.no_alias_cache:
                status = cached_alias(alias)
            if status is None:
                if not key:
                    status, detail = "unprobeable", f"нет ключа ({key_source})"
                else:
                    status, detail = probe_alias(endpoint, key, alias)
                    if status in ("ok", "provider-error"):
                        cache_alias(alias, status)
            if status == "ok":
                continue
            if status == "provider-error":
                for agent in agents:
                    findings.append({"agent": agent,
                                     "pin": f"{GATEWAY_PROVIDER_ID}/{alias}",
                                     "reason": "MISSING_AT_PROVIDER",
                                     "detail": f"живая проба: провайдер не отдаёт ({detail})"})
                continue
            for agent in agents:
                findings.append({"agent": agent, "pin": f"{GATEWAY_PROVIDER_ID}/{alias}",
                                 "reason": "ALIAS_NOT_PROBED",
                                 "detail": f"живая проба не дала вердикта ({detail or status})"})

    warnings.extend(r109_conflicts(aliases))
    return findings, warnings


def evaluate_pins(pins: list[tuple[str, str]], catalog: set[tuple[str, str]],
                  providers: set[str], provider_state: dict[str, set[str]],
                  provider_errors: dict[str, str]) -> list[dict]:
    """Вердикты по обоим источникам: каталог OpenCode + провайдерный список."""
    findings: list[dict] = []
    for agent, pin in pins:
        parts = split_pin(pin)
        if parts is None:
            findings.append({"agent": agent, "pin": pin, "reason": "MALFORMED"})
            continue
        prov, mid = parts
        if (prov, mid) not in catalog:
            reason = "MISSING_PROVIDER" if prov not in providers else "MISSING_MODEL"
            findings.append({"agent": agent, "pin": pin, "reason": reason})
            continue
        if prov == GATEWAY_PROVIDER_ID:
            continue  # алиасы шлюза проверяет check_aliases()
        if prov in provider_errors:
            findings.append({"agent": agent, "pin": pin, "reason": "UNPROBEABLE",
                             "detail": provider_errors[prov]})
            continue
        known = provider_state.get(prov)
        if known is None:
            continue
        if normalize_id(mid) not in known:
            findings.append({"agent": agent, "pin": pin,
                             "reason": "MISSING_AT_PROVIDER",
                             "detail": f"провайдер {prov} на нашем ключе не отдаёт {mid}"})
    return findings



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
    parser.add_argument("--no-provider-check", action="store_true",
                        help="не проверять провайдерный список моделей (источник 2)")
    parser.add_argument("--provider-models-file", default=None,
                        help="файл со списками моделей {provider: [id]} — вместо сети")
    parser.add_argument("--provider-endpoints", default=None,
                        help="файл с эндпоинтами {provider: {endpoint, env}}")
    parser.add_argument("--gateway-endpoint", default=None,
                        help="эндпоинт шлюза алиасов (по умолчанию — из каталога)")
    parser.add_argument("--no-alias-probe", action="store_true",
                        help="не делать живую чат-пробу алиасов")
    parser.add_argument("--no-alias-cache", action="store_true",
                        help="не использовать кэш живой пробы алиасов")
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

    if not catalog:
        # Пустой ответ сервера неотличим от сломанного сервера: трактовать его
        # как «все модели исчезли» нельзя (ложная тревога на весь флот), молча
        # пропускать — тоже нельзя. Явный WARN и пропуск проверки.
        print("pin-check: WARN — каталог пуст (модели не вернулись); проверка пропущена")
        write_report(source, pins, [], "SKIPPED_EMPTY_CATALOG")
        return 0

    # Источник 2: провайдерный список моделей на НАШЕМ ключе + живая проба
    # алиаса шлюза (спека docs/specs/pin-guard.md §4.1, BF-20261120-01).
    provider_state: dict[str, set[str]] = {}
    provider_errors: dict[str, str] = {}
    r109_warnings: list[str] = []
    if not args.no_provider_check:
        provider_state, provider_errors = collect_provider_state(pins, args)
    findings = evaluate_pins(pins, catalog, providers, provider_state,
                             provider_errors)
    if not args.no_provider_check:
        alias_findings, r109_warnings = check_aliases(pins, args)
        findings.extend(alias_findings)

    blocking = [f for f in findings if f["reason"] in BLOCKING_REASONS]
    soft = [f for f in findings if f["reason"] in WARN_REASONS]

    # Diff-гейт: в --staged блокируем только НОВЫЕ битые пины; уже сломанный
    # пин (решение ещё не принято) остаётся громким, но не блокирует чужие
    # коммиты — иначе один старый пин встанет весь флот.
    known: list[dict] = list(soft)
    new: list[dict] = blocking
    if args.staged and not args.strict:
        baseline = pins_from_ref(args.baseline, Path(args.repo))
        baseline_findings = evaluate_pins(baseline, catalog, providers,
                                          provider_state, provider_errors)
        if not args.no_provider_check:
            base_alias_findings, _ = check_aliases(baseline, args)
            baseline_findings.extend(base_alias_findings)
        baseline_broken = {f["pin"] for f in baseline_findings
                           if f["reason"] in BLOCKING_REASONS}
        new = [f for f in blocking if f["pin"] not in baseline_broken]
        known = [f for f in blocking if f["pin"] in baseline_broken] + soft

    status = "FAIL" if new else ("WARN" if (known or r109_warnings) else "PASS")
    write_report(source, pins, findings, status, extra={
        "provider_errors": provider_errors,
        "r109_warnings": r109_warnings,
    })

    if args.json:
        print(json.dumps({
            "source": source, "status": status, "pins_total": len(pins),
            "new_findings": new, "known_findings": known,
            "provider_errors": provider_errors,
            "r109_warnings": r109_warnings},
            ensure_ascii=False, indent=2))
    else:
        for item in new:
            print(f"  ❌ {item['agent']}: {item['pin']} — {item['reason']}"
                  + (f" ({item['detail']})" if item.get("detail") else ""))
        for item in known:
            if item["reason"] in WARN_REASONS:
                print(f"  ⚠️  {item['agent']}: {item['pin']} — {item['reason']}"
                      + (f" ({item['detail']})" if item.get("detail") else ""))
            else:
                print(f"  ⚠️  {item['agent']}: {item['pin']} — {item['reason']} "
                      f"(бит и до этого коммита — решение по нему не принято)")
        for warning in r109_warnings:
            print(f"  ⚠️  {warning}")
        if new:
            print(f"pin-check: FAIL — {len(new)} НОВЫХ битых пин(ов) ({source}); "
                  f"модель вне каталога = тихий фолбэк на дефолт агента")
        elif known or r109_warnings:
            print(f"pin-check: WARN — {len(known)} ранее битых/непроверяемых пин(ов) "
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

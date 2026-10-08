#!/usr/bin/env python3
"""model-watch: zero-LLM monitors of provider model catalogs.

Тянет https://models.dev/api.json, сверяет с provider-блоком opencode.jsonc
и встроенными провайдерами opencode/opencode-go, пишет снапшот
control-plane/model-catalog.json в vault и печатает дельту к предыдущему.

Запуск: python3 model-watch.py [--offline <api.json>]
Env:    MODEL_WATCH_CONFIG   путь до opencode.jsonc
        MODEL_WATCH_SNAPSHOT путь до снапшота
"""
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOTFILES = HERE.parent.parent
DEFAULT_CONFIG = DOTFILES / "opencode-global/.config/opencode/opencode.jsonc"
DEFAULT_SNAPSHOT = Path.home() / "Projects/OpenCode-Vault/control-plane/model-catalog.json"
API_URL = "https://models.dev/api.json"
# Встроенные провайдеры OpenCode: не объявлены в конфиге, но резолвятся runtime.
BUILTIN_PROVIDERS = ("opencode", "opencode-go")


def load_jsonc(path: Path) -> dict:
    """Минимальный JSONC: снимаем //-комментарии и висячие запятые."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r"//[^\"\\]*$", "", text, flags=re.M)  # trailing comments
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


def tracked_providers(cfg: dict) -> dict:
    """declared provider id -> set(model ids) из блока provider (старая схема)."""
    out = {}
    for pid, pdef in (cfg.get("provider") or {}).items():
        out[pid] = set((pdef.get("models") or {}).keys())
    for pid in BUILTIN_PROVIDERS:
        out.setdefault(pid, set())
    return out


def fetch_api(offline: str | None) -> dict:
    if offline:
        return json.loads(Path(offline).read_text(encoding="utf-8"))
    # models.dev отдаёт 403 на стандартный urllib-агент, нужен явный заголовок User-Agent
    req = urllib.request.Request(API_URL, headers={"User-Agent": "model-watch/1.0 (ecosys refresh daemon)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def build_snapshot(api: dict, declared: dict) -> dict:
    providers = {}
    for pid, cfg_models in sorted(declared.items()):
        cat_models = (api.get(pid) or {}).get("models") or {}
        models = {}
        for mid in sorted(set(cfg_models) | set(cat_models)):
            m = cat_models.get(mid) or {}
            cost = m.get("cost") or {}
            c_in = cost.get("input")
            c_out = cost.get("output")
            models[mid] = {
                "in": mid in cat_models,  # есть в апстрим-каталоге models.dev
                "cost_in": c_in,
                "cost_out": c_out,
                "free": bool(c_in == 0 and c_out == 0) if c_in is not None else False,
            }
        providers[pid] = {"models": models}
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "providers": providers,
    }


def diff(old: dict, new: dict) -> list[str]:
    lines = []
    op, np_ = old.get("providers", {}), new.get("providers", {})
    for pid in sorted(set(op) | set(np_)):
        om = op.get(pid, {}).get("models", {})
        nm = np_.get(pid, {}).get("models", {})
        for mid in sorted(set(nm) - set(om)):
            lines.append(f"+ {pid}/{mid} (прибыло)")
        for mid in sorted(set(om) - set(nm)):
            lines.append(f"- {pid}/{mid} (убыло)")
        for mid in sorted(set(om) & set(nm)):
            o, n = om[mid], nm[mid]
            if not o.get("free") and n.get("free"):
                lines.append(f"~ {pid}/{mid} стало бесплатным")
            elif o.get("cost_in") != n.get("cost_in") or o.get("cost_out") != n.get("cost_out"):
                lines.append(f"~ {pid}/{mid} цена {o.get('cost_in')}/{o.get('cost_out')} -> {n.get('cost_in')}/{n.get('cost_out')}")
            elif o.get("in") != n.get("in"):
                lines.append(f"~ {pid}/{mid} в каталоге: {n.get('in')}")
    return lines


def main() -> int:
    offline = None
    if "--offline" in sys.argv:
        offline = sys.argv[sys.argv.index("--offline") + 1]
    cfg_path = Path(os.environ.get("MODEL_WATCH_CONFIG", DEFAULT_CONFIG))
    snap_path = Path(os.environ.get("MODEL_WATCH_SNAPSHOT", DEFAULT_SNAPSHOT))
    cfg = load_jsonc(cfg_path)
    api = fetch_api(offline)
    new = build_snapshot(api, tracked_providers(cfg))
    old = json.loads(snap_path.read_text()) if snap_path.exists() else {"providers": {}}
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_path.write_text(json.dumps(new, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = diff(old, new)
    n_models = sum(len(p["models"]) for p in new["providers"].values())
    print(f"snapshot: {snap_path} providers={len(new['providers'])} models={n_models} at {new['generated_at']}")
    print(f"delta к предыдущему снапшоту: {len(lines)} изменений")
    for ln in lines:
        print(" ", ln)
    return 0


if __name__ == "__main__":
    sys.exit(main())

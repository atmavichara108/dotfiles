#!/usr/bin/env python3
"""agent-perms check — страж экспозиции инструментов (инцидент 2026-10-25).

История: новый формат политик в opencode.jsonc (`permissions:
[{action, resource, effect}]`) содержал deny-правила для shell, но НЕ
содержал allow-all. Инструмент shell перестал экспонироваться («No tool
named shell is currently available») — у всех агентов, грузящихся через
этот конфиг. Тот же класс сломал владельцу нервы месяц назад.

Этот сторож проверяет инвариант и вызывается pre-commit'ом и вручную:

1. глобальный opencode.jsonc (opencode-global): в массиве policies есть
   allow-all для критичных инструментов: shell, edit, read, glob, grep;
2. ВСЕ агентские .md (repo + волт) парсятся как YAML-шапка; блок
   permission содержит минимально необходимые ключи и не имеет
   «безопасной» ловушки: catch-all deny в bash/shell без allow-форм;
3. agent-файл без permission-tools вообще → WARN (агент молча лишён
   инструментов).

Выход: 0 = ок, 1 = нарушение. Без сети и зависимостей (stdlib + pyyaml).
"""
import json
import os
import re
import sys

REPO = os.path.expanduser("~/dotfiles")
GLOBAL_CFG = os.path.join(REPO, "opencode-global/.config/opencode/opencode.jsonc")
VAULT = os.path.expanduser("~/Projects/OpenCode-Vault")

REQUIRED_ALLOW = ["shell", "edit", "read", "glob", "grep"]
DANGEROUS_CATCHALL = ("bash", "shell")


def strip_jsonc(text):
    """Минимальный JSONC→JSON: убрать //-комментарии и хвостовые запятые."""
    text = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def check_global():
    problems = []
    try:
        cfg = json.loads(strip_jsonc(open(GLOBAL_CFG, encoding="utf-8").read()))
    except Exception as e:  # noqa: BLE001
        return [f"глобальный конфиг не парсится: {e}"]
    pol = cfg.get("permissions")
    if isinstance(pol, list):
        for action in REQUIRED_ALLOW:
            has_allow = any(
                p.get("action") == action and p.get("effect") == "allow"
                and p.get("resource") in ("*", None)
                for p in pol if isinstance(p, dict)
            )
            if not has_allow:
                problems.append(
                    f"policies: нет allow-all для «{action}» (есть только deny) — "
                    f"инструмент будет скрыт. Добавь "
                    f'{{ "action": "{action}", "resource": "*", "effect": "allow" }}')
    perm = cfg.get("permission")
    if isinstance(perm, dict):
        for action in ("bash", "shell"):
            block = perm.get(action)
            if isinstance(block, dict) and block.get("*") == "deny":
                problems.append(
                    f"permission.{action}: catch-all «*»: deny — старая ловушка "
                    f"(инструмент может не экспонироваться). Форма: allow + deny-list.")
    return problems


def policies_index():
    """action -> [(resource, effect)] из глобального policies."""
    try:
        cfg = json.loads(strip_jsonc(open(GLOBAL_CFG, encoding="utf-8").read()))
    except Exception:  # noqa: BLE001
        return {}
    out = {}
    for p in (cfg.get("permissions") or []):
        if isinstance(p, dict) and p.get("action"):
            out.setdefault(p["action"], []).append(
                (p.get("resource"), p.get("effect")))
    return out


def iter_agent_files():
    for root, dirs, files in os.walk(os.path.join(REPO, ".opencode/agent")):
        dirs[:] = [d for d in dirs if d != "node_modules"]
        for f in files:
            if f.endswith(".md"):
                yield os.path.join(root, f)
    for base in ("agent", "agents"):
        d = os.path.join(VAULT, ".opencode", base)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.endswith(".md"):
                    yield os.path.join(d, f)


def check_agents():
    problems = []
    try:
        import yaml
    except ImportError:
        print("WARN: pyyaml не установлен — проверка агентских файлов пропущена")
        return problems
    for path in iter_agent_files():
        try:
            s = open(path, encoding="utf-8").read()
            fm = s.split("---")[1]
            d = yaml.safe_load(fm)
        except Exception as e:  # noqa: BLE001
            problems.append(f"{path}: шапка не парсится ({e}) — агент не загрузится")
            continue
        if not isinstance(d, dict):
            problems.append(f"{path}: шапка не словарь")
            continue
        perm = d.get("permission")
        if not isinstance(perm, dict):
            problems.append(f"{path}: нет блока permission — агент молча лишён инструментов")
            continue
        for key in DANGEROUS_CATCHALL:
            block = perm.get(key)
            if isinstance(block, dict) and block.get("*") == "deny":
                problems.append(
                    f"{path}: permission.{key} catch-all deny — старая ловушка "
                    f"(форма: allow + deny-list опасных)")
        # Канон Мастерской (inc-shell вердикт): инструмент, упомянутый в
        # агентском файле, обязан иметь allow в глобальном слое — иначе
        # агентский файл бессилен (класс инцидента shell). Allow считается
        # и из policies (массив), и из старого стиля permission.<tool>.
        pol = policies_index()
        legacy = global_legacy_permissions()
        for tool, spec in perm.items():
            if tool in ("doom_loop",):
                continue
            pol_ok = any(e == "allow" for _, e in pol.get(tool, []))
            leg = legacy.get(tool)
            leg_ok = leg == "allow" or (isinstance(leg, dict)
                                        and leg.get("*") == "allow")
            if spec not in (None, "deny") and not pol_ok and not leg_ok:
                problems.append(
                    f"{path}: permission.{tool} есть в агенте, но в глобальном "
                    f"слое (policies и permission) нет allow — агентский файл "
                    f"бессилен (класс инцидента shell). Добавь allow-all.")
    return problems


def global_legacy_permissions():
    """Старый стиль: permission.<tool> в глобальном opencode.jsonc."""
    try:
        cfg = json.loads(strip_jsonc(open(GLOBAL_CFG, encoding="utf-8").read()))
    except Exception:  # noqa: BLE001
        return {}
    p = cfg.get("permission")
    return p if isinstance(p, dict) else {}


def main():
    problems = check_global() + check_agents()
    if problems:
        print("agent-perms: НАРУШЕНИЯ ИНВАРИАНТА:")
        for p in problems:
            print(" -", p)
        return 1
    print("agent-perms: OK (глобал + агентские файлы)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""gravewalk — протокол архивации могильников (Task 2 Лабы, мандат ЦУ
gravewalk-protocol-mandate 2026-10-30; спека lab-gravewalk-task2.md).

Два могильника с телеметрией без жизненного цикла:
1. Карточки decision-queue (effect=allow + вечный pending) — авто-закрытие
   resolved-auto возрастом >1 дня; high/critical-with-allow — ТОЛЬКО метка
   (выборочная сверка владельцем 30 шт. — его слово, спец-пункт ЦУ);
2. Инциденты: recommended_route=retry-then-stop и возраст >7 дней без
   действий → экспорт в архив со счётчиком; provider-timeout/quota →
   агрегат для Ротатора (вход health Q-005).

Механика: append-only (история не удаляется), таймер по образу
doctrine-flush. Приёмка чисел — Лаба (её инструмент, её kill-критерий).
"""
import argparse
import json
import os
import time

CARDS = os.path.expanduser(
    "~/.local/state/opencode/decision-queue/cards")
INCIDENTS = os.path.expanduser("~/.local/state/opencode/incidents")
ARCHIVE = os.path.expanduser(
    "~/.local/state/opencode/gravewalk/archive.jsonl")
AGGREGATE = os.path.expanduser(
    "~/.local/state/opencode/gravewalk/provider-agg.jsonl")
STATE = os.path.expanduser("~/.local/state/opencode/gravewalk/state.json")

CARD_MAX_AGE_D = 1.0
INCIDENT_MAX_AGE_D = 7.0
PROTECTED_RISKS = ("high", "critical")

# Канон Р-035 (danger-patterns.md, слово владельца 2026-10-30):
# детерминированный сканер вместо выборочного чтения глазами.
# Попадание = исключение → только владельцу; не попало = шум → авто-закрытие.
DANGER_PATTERNS = {
    "удаление": ["rm -rf", "git reset --hard", "git clean", "git branch -D"],
    "секреты": ["~/.secrets", ".env", "токен", "ключ", "парол"],
    "наружу": ["git push", "curl", "wget", "smtp", "resend"],
    "полномочия": ["sudo", "chmod", "systemctl", "ssh"],
    "чужая-зона": [".mcode/", ".ssh/", "~/.config/opencode"],
    "обход-гейтов": ["GARBAGE_OK=1", "FRONTMATTER_OK=1", "MIXED_OK=1",
                     "AGENT_PERMS_OK=1", "MOJIBAKE_OK=1", "--force"],
}


ALLOWED_WORK = [
    # уточнение политики (аудит ЦУ 327, Р-035, 2026-10-30): allowed-work,
    # а не исключения — иначе панель заливает ложным.
    ("git push в свои репо (на своей ветке)", "git push"),
    ("rm в /tmp/opencode (своя песочница)", "/tmp"),
    ("read-only команды со словом секрет (поиск, не утечка)",
     "rg"), ("read-only команды со словом секрет (поиск, не утечка)", "grep"),
    ("read-only команды со словом секрет (поиск, не утечка)", "cat"),
    ("read-only команды со словом секрет (поиск, не утечка)", "echo"),
    ("осознанный обход гейта с причиной", "GARBAGE_OK"),
    ("осознанный обход гейта с причиной", "MIXED_OK"),
    ("осознанный обход гейта с причиной", "MOJIBAKE_OK"),
]


def _allowed_match(d):
    """Allowed-work (не исключение): сначала эта проверка."""
    blob = " ".join(str(d.get(k, "")) for k in ("pattern", "reason", "title"))
    low = blob.lower()
    for label, needle in ALLOWED_WORK:
        if needle.lower() in low:
            if needle == "/tmp" and "/tmp/opencode" not in low:
                continue  # rm где угодно, кроме песочницы — не allowed
            if needle == "git push":
                repos = ("dotfiles", "opencode-vault", "ability-lab",
                         "dv-hub", "ssa")
                if not any(r in low for r in repos):
                    continue
            return label
    return None


def _danger_match(d):
    """Первое попадание под паттерн (или None). Ищем в pattern/reason/title."""
    blob = " ".join(str(d.get(k, "")) for k in ("pattern", "reason", "title"))
    for label, needles in DANGER_PATTERNS.items():
        for n in needles:
            if n.lower() in blob.lower():
                return f"{label}:{n}"
    return None


def _age_d(ts):
    """Возраст в днях: unix-int или ISO-строка."""
    if isinstance(ts, (int, float)):
        return (time.time() - float(ts)) / 86400.0
    try:
        t = time.mktime(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:  # noqa: BLE001
        return 0.0
    return (time.time() - t) / 86400.0


def _append(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def scan_cards(write=False):
    """Карточки: resolved-auto / protected-mark."""
    stats = {"total": 0, "auto": 0, "protected": 0, "exception": 0,
             "allowed_work": 0, "kept": 0}
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for fn in sorted(os.listdir(CARDS)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(CARDS, fn)
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        stats["total"] += 1
        if d.get("status") != "pending":
            stats["kept"] += 1
            continue
        effect = str(d.get("effect", ""))
        ok = effect in ("allow", "'allow'", "\"allow\"")
        age = _age_d(d.get("created", ""))
        if not (ok and age > CARD_MAX_AGE_D):
            stats["kept"] += 1
            continue
        risk = str(d.get("risk", "")).lower()
        if risk in PROTECTED_RISKS:
            # Политика Р-035: сканер по danger-patterns. Попадание =
            # исключение (показ владельцу); не попало = авто-закрытие
            # с меткой policy-pass.
            aw = _allowed_match(d)
            if aw:
                # allowed-work = шум по политике (аудит ЦУ) → авто-закрытие
                # с меткой причины (не исключение, не вечный pending).
                d["status"] = "resolved-auto"
                d["resolved_auto_ts"] = now_iso
                d["gravewalk_allowed"] = aw
                if write:
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(d, f, ensure_ascii=False)
                    _append(ARCHIVE, {"ts": now_iso, "kind": "card-allowed",
                                      "id": d.get("id"), "allowed": aw,
                                      "age_d": round(age, 1)})
                stats["allowed_work"] += 1
                stats["auto"] += 1
                continue
            hit = _danger_match(d)
            if hit:
                if not d.get("gravewalk_exception"):
                    d["gravewalk_exception"] = now_iso
                    if write:
                        with open(path, "w", encoding="utf-8") as f:
                            json.dump(d, f, ensure_ascii=False)
                    _append(os.path.expanduser(
                        "~/.local/state/opencode/gravewalk/exceptions.jsonl"),
                        {"ts": now_iso, "id": d.get("id"), "risk": risk,
                         "match": hit, "age_d": round(age, 1),
                         "pattern": str(d.get("pattern", ""))[:200],
                         "note": "исключение Р-035: показ владельцу"})
                stats["exception"] = stats.get("exception", 0) + 1
                continue
            d["gravewalk_policy_pass"] = now_iso
        d["status"] = "resolved-auto"
        d["resolved_auto_ts"] = now_iso
        if write:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)
        _append(ARCHIVE, {"ts": now_iso, "kind": "card-auto",
                          "id": d.get("id"), "age_d": round(age, 1)})
        stats["auto"] += 1
    return stats


def scan_incidents(write=False):
    """Инциденты: expire retry-then-stop >7д + агрегат provider-*."""
    stats = {"total": 0, "expired": 0, "provider_agg": 0}
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not os.path.isdir(INCIDENTS):
        return stats
    for fn in sorted(os.listdir(INCIDENTS)):
        if not fn.endswith(".djsonl") or fn == "_archive":
            continue
        path = os.path.join(INCIDENTS, fn)
        for line in open(path, encoding="utf-8"):
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            stats["total"] += 1
            stats["events"] = stats.get("events", 0) + int(d.get("count", 1) or 1)
            cls = d.get("error_class", "")
            ts = d.get("ts") or d.get("first_ts") or 0
            age = _age_d(ts)
            route = d.get("recommended_route", "")
            if cls.startswith("provider-") and age > INCIDENT_MAX_AGE_D:
                if not write:
                    stats["provider_agg"] += 1
                    continue
                _append(AGGREGATE, {"ts": now_iso, "cls": cls,
                                    "project": d.get("project_slug", ""),
                                    "count": d.get("count", 1),
                                    "session": d.get("session_id", "")[:22]})
                stats["provider_agg"] += 1
            if route.startswith("workflow-retry-then-stop") \
                    and age > INCIDENT_MAX_AGE_D:
                if write:
                    _append(os.path.expanduser(
                        "~/.local/state/opencode/gravewalk/expired.jsonl"),
                        {"ts": now_iso, "capture_id": d.get("capture_id"),
                         "cls": cls, "age_d": round(age, 1),
                         "note": "retry-then-stop >7д без действий"})
                stats["expired"] += 1
    return stats



def apply_labels(write=False):
    """Ярлыки классов от Мастерской (gravewalk 2026-10-30):
    provider-error-generic + route=sysop-report → provider-quota
    (opencode-go, primary); записи >14д — expire с меткой classified.
    Append-only: исходные строки не трогаем, ярлыки — в labels.jsonl."""
    labels = []
    stats = {"labeled": 0, "expired_classified": 0}
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if not os.path.isdir(INCIDENTS):
        return stats
    for fn in sorted(os.listdir(INCIDENTS)):
        if not fn.endswith(".djsonl") or fn == "_archive":
            continue
        for line in open(os.path.join(INCIDENTS, fn), encoding="utf-8"):
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if d.get("safe_hint") != "provider-error-generic":
                continue
            if not str(d.get("recommended_route", "")).startswith("sysop-report"):
                continue
            cid = d.get("capture_id", "")
            labels.append({"ts": now_iso, "capture_id": cid,
                           "class": "provider-quota",
                           "primary": "opencode-go",
                           "source_hint": d.get("safe_hint"),
                           "events": int(d.get("count", 1) or 1),
                           "labeled_by": "Мастерская (gravewalk разбор)"})
            stats["labeled"] += 1
            age = _age_d(d.get("ts") or d.get("first_ts") or 0)
            if age > 14 and write:
                _append(os.path.expanduser(
                    "~/.local/state/opencode/gravewalk/expired.jsonl"),
                    {"ts": now_iso, "capture_id": cid,
                     "cls": "provider-quota", "age_d": round(age, 1),
                     "note": "classified+expired (retry-then-stop исполнен)"})
                stats["expired_classified"] += 1
    if write:
        for lb in labels:
            _append(os.path.expanduser(
                "~/.local/state/opencode/gravewalk/labels.jsonl"), lb)
    return stats


def main():
    p = argparse.ArgumentParser(prog="gravewalk")
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    cs = scan_cards(write=args.write)
    ins = scan_incidents(write=args.write)
    ls = apply_labels(write=args.write)
    verdict = {"cards": cs, "incidents": ins, "labels": ls,
               "write": args.write}
    print("GRAVEWALK " + json.dumps(verdict, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

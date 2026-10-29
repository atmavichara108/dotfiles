#!/usr/bin/env python3
"""probe-rotator — расписанная телеметрия провайдеров (DoD-2 «health по
расписанию», ответ УАСу/ЦУ на запрос probe.timer).

Читает провайдеров из ~/.config/promo-provider-probe/config.json и для
каждого вызывает promo-provider-probe с --json (read-only, без smoke —
кредиты не тратятся). Результаты пишет в
~/.local/state/opencode/rotator/probe-<UTC-ts>.json (+ latest.json).
Не прошёл ни один провайдер (сеть/auth) — отличивый инцидент в
journal.jsonl (меты-only). Секреты не пишутся и не печатаются (сама
проба это гарантирует — она выводит только коды/структуры).

Запуск: systemd probe.timer (default 3600с) или вручную:
  python3 probe-rotator.py [--only <provider_id>...]
"""
import json
import os
import subprocess
import sys
import time

CONFIG = os.path.expanduser("~/.config/promo-provider-probe/config.json")
PROBE = os.path.expanduser("~/dotfiles/scripts/.local/bin/promo-provider-probe")
OUT_DIR = os.path.expanduser("~/.local/state/opencode/rotator")
JOURNAL = os.path.join(OUT_DIR, "journal.jsonl")
# Вердикт ЦУ 2026-10-29 (portal-formalities-done п.4): канонический писатель
# журнала телеметрии — ОДИН (зонд УАСа, control-plane/telemetry/provider-
# health.jsonl). Эта проба остаётся ЛОКАЛЬНЫМ кэшем: пишет только в state
# (~/.local/state/opencode/rotator/), в волт-журнал — НИКОГДА по умолчанию.
# Запись в волт возможна лишь явным opt-in (VAULT_TELEMETRY=1) для отладки.
VAULT_TELEMETRY = os.environ.get(
    "VAULT_TELEMETRY",
    "" if os.environ.get("VAULT_TELEMETRY_OPT_IN") != "1" else
    os.path.expanduser(
        "~/Projects/OpenCode-Vault/control-plane/telemetry/provider-health.jsonl"))


def providers():
    try:
        cfg = json.load(open(CONFIG, encoding="utf-8"))
        return list((cfg.get("providers") or {}).keys())
    except Exception:  # noqa: BLE001
        return []


def journal(row):
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def probe(pid):
    try:
        r = subprocess.run([sys.executable, PROBE, pid, "--json"],
                           capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001
        return {"provider_id": pid, "status": "ERROR",
                "models_count": 0, "usable_balance": None,
                "balance_kind": None, "warnings": [type(e).__name__]}
    out = (r.stdout or "").strip()
    try:
        d = json.loads(out)
        d.setdefault("provider_id", pid)
        d["source"] = "probe-rotator"
        return d
    except Exception:  # noqa: BLE001
        return {"provider_id": pid, "status": "UNPARSED",
                "models_count": 0, "usable_balance": None,
                "balance_kind": None, "warnings": ["unparsed"],
                "source": "probe-rotator"}


def telemetry_line(row, ts):
    """Строка в формате УАС-стандарта (те же ключи; секретов нет —
    probe выводит только коды/структуры).

    Канон классификации (УАС, коммит 302073b6, 2026-10-27): статус описывает
    доступность/качество ОТВЕТА; баланс и латентность — отдельные
    nullable-поля. Поэтому DEGRADED, причиной которого является ТОЛЬКО
    неизвестный баланс, в канонической строке → ACTIVE с
    usable_balance: null (отсутствие данных — пустое поле, не состояние).
    """
    status = row.get("status")
    warnings = list(row.get("warnings") or [])
    balance_only = warnings and all(
        any(k in w.lower() for k in ("balance", "баланс")) for w in warnings)
    if status == "DEGRADED" and balance_only:
        status = "ACTIVE"
        warnings = warnings + ["canon:balance-unknown-not-degraded"]
    return {
        "ts": ts,
        "provider_id": row.get("provider_id") or row.get("provider"),
        "status": status,
        "models_count": row.get("models_count"),
        "usable_balance": row.get("usable_balance"),
        "balance_kind": row.get("balance_kind"),
        "warnings": warnings,
        "latency_ms": row.get("latency_ms"),
        "redacted": True,
        "source": "probe-rotator",
    }


def vault_append(rows, ts):
    """Опциональная (opt-in) сводка в волт — по умолчанию выключена."""
    if not VAULT_TELEMETRY:
        return False
    try:
        os.makedirs(os.path.dirname(VAULT_TELEMETRY), exist_ok=True)
        with open(VAULT_TELEMETRY, "a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(telemetry_line(row, ts),
                                   ensure_ascii=False) + "\n")
        return True
    except Exception as e:  # noqa: BLE001
        journal({"ts": int(time.time()), "class": "telemetry-append-failed",
                 "path": VAULT_TELEMETRY, "reason": type(e).__name__})
        return False


def main(argv):
    only = []
    if "--only" in argv:
        i = argv.index("--only")
        only = [a for a in argv[i + 1:] if not a.startswith("--")]
        argv = argv[:i]
    pids = providers()
    if not pids:
        print("probe-rotator: нет провайдеров в конфиге — нечего зондировать")
        return 0
    if only:
        pids = [p for p in pids if p in only]
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ts_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    rows = [probe(pid) for pid in pids]
    canon = [telemetry_line(r, ts_iso) for r in rows]
    ok = sum(1 for r in canon if r.get("status") == "ACTIVE")
    vault_append(rows, ts_iso)
    payload = {"ts": ts, "providers": rows,
               "summary": {"total": len(rows), "active": ok}}
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"probe-{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    with open(os.path.join(OUT_DIR, "latest.json"), "w",
              encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    if ok == 0:
        journal({"ts": int(time.time()), "class": "probe-all-failed",
                 "providers": pids,
                 "note": "ни один провайдер не активен (сеть/auth)"})
    print(f"probe-rotator: {path} — active {ok}/{len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

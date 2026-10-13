#!/usr/bin/env python3
"""orch-guard — CLI-учёт оркестрации поверх ledger (append-only JSONL).

Данные ВНЕ репозитория: ~/.local/state/opencode/orch-guard/ledger.jsonl
(stdlib only).

Команды:
    dispatch --task ID --agent A --zone Z [--model M] [--retry N]
             [--force-wave --reason R] [--primary-model P] [--root D]
    complete --task ID --result PASS|FAIL|BLOCKED|STOP [--root D]
    verdict  --task ID --result PASS|FAIL --by verifier [--root D]
    status [--root D]
    selftest

Отказы dispatch (rc=2, причина на русском):
    (а) уже 3 активные задачи с пересекающимися зонами
        (зоны пересекаются = равны или одна префикс другой;
        researcher/verifier — всегда можно, и в счётчик не входят);
    (б) retry N>=2 без --force-wave (--force-wave требует --reason);
    (в) --model содержит "free" и primary-модель тоже free —
        «пин на free роняет вызов, иди без пина» (урок 2026-10-14).
        primary-модель: флаг --primary-model, иначе env
        ORCH_GUARD_PRIMARY_MODEL, иначе дефолт (free-модель sysop).
Секреты в полях записи: эвристика-отказ как в hotmem/helpctl (rc=3).

Активная задача = есть dispatch без закрывающего complete.
Ledger — append-only: пишем РОВНО одну строку (режим "a"), не перезаписываем.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".local" / "state" / "opencode" / "orch-guard"
LEDGER_NAME = "ledger.jsonl"
DEFAULT_PRIMARY_MODEL = "opencode/muse-spark-1.3-contributor-free"

RESULTS_COMPLETE = ("PASS", "FAIL", "BLOCKED", "STOP")
RESULTS_VERDICT = ("PASS", "FAIL")
FREE_AGENTS = ("researcher", "verifier")
MAX_OVERLAP = 3

# Эвристика секретов — канон helpctl SECRET_PATTERNS (укорочено, формы те же).
SECRET_PATTERNS = (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|auth[_-]?token|client[_-]?secret)\b\s*[:=]",
    r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}",
    r"\bsk-[A-Za-z0-9]{16,}",
    r"\bghp_[A-Za-z0-9]{20,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"(?i)\bssh-(?:rsa|ed25519|dss)\s+AAAA[A-Za-z0-9+/]{20,}",
    r"\bAIza[0-9A-Za-z_-]{30,}",
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
)


def eprint(*a: object) -> None:
    print(*a, file=sys.stderr)


def ledger_path(root: Path) -> Path:
    return root / LEDGER_NAME


def secret_hit(text: str) -> str | None:
    """Первый совпавший секретоподобный фрагмент (до 60 символов) или None."""
    for pat in SECRET_PATTERNS:
        m = re.search(pat, text)
        if m:
            return m.group(0)[:60]
    return None


def zones_overlap(a: str, b: str) -> bool:
    """Равны или одна — префикс другой по сегментам (/ или . или :)."""
    a, b = a.strip().strip("/"), b.strip().strip("/")
    if a == b:
        return True
    for sep in ("/", ".", ":"):
        if a.startswith(b + sep) or b.startswith(a + sep):
            return True
    # общий случай: строковый префикс по границе слова
    if a.startswith(b) or b.startswith(a):
        short, long = (a, b) if len(a) < len(b) else (b, a)
        if long.startswith(short) and long[len(short):len(short) + 1] in "/.:-_":
            return True
    return False


def load_events(root: Path) -> list[dict]:
    """Прочитать ledger построчно; битые строки пропускаем (не падаем)."""
    path = ledger_path(root)
    if not path.exists():
        return []
    events: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                events.append(obj)
    return events


def active_dispatches(events: list[dict]) -> dict[str, dict]:
    """task -> последний dispatch, если не закрыт complete."""
    active: dict[str, dict] = {}
    for ev in events:
        kind = ev.get("event")
        task = ev.get("task", "")
        if kind == "dispatch" and task:
            active[task] = ev
        elif kind == "complete" and task in active:
            del active[task]
    return active


def append_event(root: Path, event: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    rec.update(event)
    line = json.dumps(rec, ensure_ascii=False, separators=(", ", ": "))
    with ledger_path(root).open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def cmd_dispatch(args: argparse.Namespace) -> int:
    task = args.task.strip()
    agent = args.agent.strip()
    zone = args.zone.strip()
    model = (args.model or "").strip()
    retry = args.retry or 0
    if not task or not agent or not zone:
        eprint("Отказ: --task, --agent и --zone обязательны и непусты.")
        return 2
    # Секреты — до записи (rc=3).
    hit = secret_hit("\n".join([task, agent, zone, model, args.reason or ""]))
    if hit:
        eprint(f"Отказ: в полях записи признак секрета ({hit}…), в ledger не пишем.")
        return 3
    # (б) retry>=2 требует --force-wave + --reason.
    if retry >= 2 and not args.force_wave:
        eprint(f"Отказ: retry={retry}≥2 без --force-wave запрещён, добавь --force-wave --reason.")
        return 2
    if args.force_wave and not (args.reason or "").strip():
        eprint("Отказ: --force-wave требует --reason.")
        return 2
    # (в) пин на free при free-primary роняет вызов.
    primary = (args.primary_model
               or os.environ.get("ORCH_GUARD_PRIMARY_MODEL", "")
               or DEFAULT_PRIMARY_MODEL)
    if model and "free" in model.lower() and "free" in primary.lower():
        eprint("Отказ: пин на free роняет вызов, иди без пина (урок 2026-10-14).")
        return 2
    # (а) пересечение зон (исследователи вне лимита).
    if agent not in FREE_AGENTS:
        events = load_events(args.root)
        active = active_dispatches(events)
        n = sum(1 for d in active.values()
                if d.get("agent") not in FREE_AGENTS
                and zones_overlap(str(d.get("zone", "")), zone))
        if n >= MAX_OVERLAP:
            eprint(f"Отказ: уже {n} активные задачи пересекаются с зоной «{zone}» (лимит {MAX_OVERLAP}).")
            return 2
    append_event(args.root, {"event": "dispatch", "task": task, "agent": agent,
                             "zone": zone, "model": model, "retry": retry,
                             "force_wave": bool(args.force_wave),
                             "reason": (args.reason or "").strip()})
    print(f"OK: dispatch {task} ({agent}, {zone}).")
    return 0


def cmd_complete(args: argparse.Namespace) -> int:
    task = args.task.strip()
    if not task:
        eprint("Отказ: --task обязателен.")
        return 2
    active = active_dispatches(load_events(args.root))
    if task not in active:
        eprint(f"Отказ: задача «{task}» не активна (нет открытого dispatch).")
        return 2
    append_event(args.root, {"event": "complete", "task": task,
                             "result": args.result})
    print(f"OK: complete {task} ({args.result}).")
    return 0


def cmd_verdict(args: argparse.Namespace) -> int:
    if (args.by or "").strip() != "verifier":
        eprint("Отказ: verdict принимает только --by verifier.")
        return 2
    task = args.task.strip()
    if not task:
        eprint("Отказ: --task обязателен.")
        return 2
    append_event(args.root, {"event": "verdict", "task": task,
                             "result": args.result, "by": "verifier"})
    print(f"OK: verdict {task} ({args.result}).")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    active = active_dispatches(load_events(args.root))
    if not active:
        print("Активных задач нет.")
        return 0
    head = f"{'TASK':<24}{'AGENT':<14}{'ZONE':<24}{'RETRY':<7}MODEL"
    print(head)
    print("-" * len(head))
    for task in sorted(active):
        d = active[task]
        print(f"{task:<24}{str(d.get('agent', '')):<14}"
              f"{str(d.get('zone', '')):<24}{str(d.get('retry', 0)):<7}"
              f"{str(d.get('model', ''))}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="orch-guard",
                                 description="CLI-учёт оркестрации поверх ledger.")
    ap.add_argument("--root", type=Path, default=None,
                    help="корень ledger (по умолчанию ~/.local/state/opencode/orch-guard)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dispatch", help="открыть задачу")
    p.add_argument("--task", required=True)
    p.add_argument("--agent", required=True)
    p.add_argument("--zone", required=True)
    p.add_argument("--model", default="")
    p.add_argument("--retry", type=int, default=0)
    p.add_argument("--force-wave", action="store_true")
    p.add_argument("--reason", default="")
    p.add_argument("--primary-model", default="")

    p = sub.add_parser("complete", help="закрыть задачу")
    p.add_argument("--task", required=True)
    p.add_argument("--result", required=True, choices=RESULTS_COMPLETE)

    p = sub.add_parser("verdict", help="вердикт приёмки (только verifier)")
    p.add_argument("--task", required=True)
    p.add_argument("--result", required=True, choices=RESULTS_VERDICT)
    p.add_argument("--by", default="")

    sub.add_parser("status", help="таблица активных задач")
    sub.add_parser("selftest", help="прогон отказов/успехов на временном корне")
    return ap


# --- selftest ---------------------------------------------------------------

def _run(argv: list[str]) -> tuple[int, str, str]:
    """Запустить себя подпроцессом, вернуть (rc, stdout, stderr)."""
    import subprocess
    r = subprocess.run([sys.executable, str(Path(__file__).resolve()), *argv],
                       capture_output=True, text=True, check=False)
    return r.returncode, r.stdout, r.stderr


def cmd_selftest() -> int:
    fails: list[str] = []

    def check(name: str, cond: bool, extra: str = "") -> None:
        print(("PASS " if cond else "FAIL ") + name + (f" — {extra}" if extra and not cond else ""))
        if not cond:
            fails.append(name + (f": {extra}" if extra else ""))

    with tempfile.TemporaryDirectory(prefix="orch-guard-test-") as tmp:
        R = ["--root", tmp]
        # 1. Успешный dispatch.
        rc, out, err = _run([*R, "dispatch", "--task", "T-1", "--agent", "bash-dev", "--zone", "scripts"])
        check("dispatch-успех", rc == 0 and "OK" in out, f"rc={rc} out={out!r} err={err!r}")
        # 2. Пересечение зон: ещё 2 в той же зоне — успех, 4-й — отказ rc=2.
        rc, _, err = _run([*R, "dispatch", "--task", "T-2", "--agent", "bash-dev", "--zone", "scripts"])
        check("dispatch-2-успех", rc == 0, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "dispatch", "--task", "T-3", "--agent", "bash-dev", "--zone", "scripts/deploy"])
        check("dispatch-префикс-успех", rc == 0, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "dispatch", "--task", "T-4", "--agent", "bash-dev", "--zone", "scripts"])
        check("dispatch-4-й-отказ", rc == 2 and "уже 3" in err, f"rc={rc} err={err!r}")
        # 3. Непересекающаяся зона — успех.
        rc, _, err = _run([*R, "dispatch", "--task", "T-5", "--agent", "bash-dev", "--zone", "qtile"])
        check("dispatch-чужая-зона-успех", rc == 0, f"rc={rc} err={err!r}")
        # 4. researcher/verifier всегда можно даже при переполнении.
        rc, _, err = _run([*R, "dispatch", "--task", "T-R", "--agent", "researcher", "--zone", "scripts"])
        check("researcher-обход", rc == 0, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "dispatch", "--task", "T-V", "--agent", "verifier", "--zone", "scripts"])
        check("verifier-обход", rc == 0, f"rc={rc} err={err!r}")
        # 5. retry>=2 без --force-wave — отказ; с флагом без reason — отказ; с reason — успех.
        rc, _, err = _run([*R, "dispatch", "--task", "T-6", "--agent", "bash-dev",
                           "--zone", "nvim", "--retry", "2"])
        check("retry-без-флага-отказ", rc == 2 and "force-wave" in err, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "dispatch", "--task", "T-6", "--agent", "bash-dev",
                           "--zone", "nvim", "--retry", "2", "--force-wave"])
        check("force-wave-без-reason-отказ", rc == 2 and "reason" in err, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "dispatch", "--task", "T-6", "--agent", "bash-dev",
                           "--zone", "nvim", "--retry", "2",
                           "--force-wave", "--reason", "вторая волна"])
        check("force-wave-с-reason-успех", rc == 0, f"rc={rc} err={err!r}")
        # 6. Пин на free при free-primary — отказ rc=2.
        rc, _, err = _run([*R, "dispatch", "--task", "T-7", "--agent", "bash-dev",
                           "--zone", "tmux", "--model", "prov/model-free"])
        check("free-пин-отказ", rc == 2 and "без пина" in err, f"rc={rc} err={err!r}")
        # 7. Тот же пин при платном primary — успех.
        env = dict(os.environ, ORCH_GUARD_PRIMARY_MODEL="paid/max-model")
        import subprocess
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()), *R,
                            "dispatch", "--task", "T-8", "--agent", "bash-dev",
                            "--zone", "tmux", "--model", "prov/model-free"],
                           capture_output=True, text=True, check=False, env=env)
        check("free-пин-при-paid-успех", r.returncode == 0, f"rc={r.returncode} err={r.stderr!r}")
        # 8. complete закрывает; повторный complete — отказ; чужой complete — отказ.
        rc, _, err = _run([*R, "complete", "--task", "T-1", "--result", "PASS"])
        check("complete-успех", rc == 0, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "complete", "--task", "T-1", "--result", "PASS"])
        check("complete-повтор-отказ", rc == 2 and "не активна" in err, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "complete", "--task", "НЕТ-ТАКОЙ", "--result", "FAIL"])
        check("complete-чужой-отказ", rc == 2 and "не активна" in err, f"rc={rc} err={err!r}")
        # 9. verdict только --by verifier.
        rc, _, err = _run([*R, "verdict", "--task", "T-2", "--result", "PASS",
                           "--by", "bash-dev"])
        check("verdict-не-verifier-отказ", rc == 2 and "verifier" in err, f"rc={rc} err={err!r}")
        rc, _, err = _run([*R, "verdict", "--task", "T-2", "--result", "PASS",
                           "--by", "verifier"])
        check("verdict-verifier-успех", rc == 0, f"rc={rc} err={err!r}")
        # 10. Секрет в полях — rc=3, в ledger не пишется.
        before = (Path(tmp) / LEDGER_NAME).read_text(encoding="utf-8")
        rc, _, err = _run([*R, "dispatch", "--task", "T-9", "--agent", "bash-dev",
                           "--zone", "zsh", "--reason", "token=ghp_12345678901234567890"])
        after = (Path(tmp) / LEDGER_NAME).read_text(encoding="utf-8")
        check("секрет-rc3", rc == 3 and "секрета" in err, f"rc={rc} err={err!r}")
        check("секрет-не-пишется", before == after, "ledger изменился")
        # 11. status показывает активные.
        rc, out, err = _run([*R, "status"])
        check("status-активные", rc == 0 and "T-2" in out and "T-1" not in out.split("T-2")[0],
              f"rc={rc} out={out!r} err={err!r}")

    if fails:
        eprint(f"SELFTEST FAIL: {len(fails)} проверок: {fails}")
        return 1
    print("SELFTEST PASS: все проверки прошли.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.root is None:
        env_root = os.environ.get("ORCH_GUARD_ROOT", "")
        args.root = Path(env_root) if env_root else DEFAULT_ROOT
    if args.cmd == "dispatch":
        return cmd_dispatch(args)
    if args.cmd == "complete":
        return cmd_complete(args)
    if args.cmd == "verdict":
        return cmd_verdict(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "selftest":
        return cmd_selftest()
    ap.error("неизвестная команда")
    return 2


if __name__ == "__main__":
    sys.exit(main())

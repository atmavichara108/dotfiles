#!/usr/bin/env python3
"""L9 — прогон набора A: актуальность источников, релевантность, тайминг.

Холодный старт (загрузка модели до первого запроса) замеряется отдельно и в
статистику 50 мс не входит. Прогон: набор A циклически, первые 5 запросов —
прогрев. Вывод: JSON-отчёт в stdout (метрики + по-запросные вердикты).
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab9  # noqa: E402

# (id, запрос, ожидаемый путь или None для пустых, ожидаемая строка или None)
SET_A = [
    ("A1", "sqlite-vec локальный векторный индекс над facts inbox session-log",
     "99-Inbox/vault-upgrade-research-2026-08-02.md", 38),
    ("A2", "stow --adopt синхронизация live и канон opencode.jsonc два расходящихся файла",
     "04-Memory/session-log/2026-09-06.md", 44),
    ("A3", "владение веткой claim-gate ADR-019 lane-правило",
     "04-Memory/session-log/2026-10-01.md", 5),
    ("A4", "peer-comms двойной ack letter.sh протокол писем",
     "04-Memory/session-log/2026-09-05.md", None),
    ("A5", "Библиотека второй brain NotebookLM кандидат-локация слово Rudra",
     "04-Memory/session-log/2026-10-13.md", 47),
    ("A6", "очередь испытаний L1-L6 Ability Lab спека Laboratory",
     "04-Memory/session-log/2026-10-13.md", 279),
    ("A7", "включение git-prune таймер за Максом открыто",
     "04-Memory/session-log/2026-10-01.md", 8),
    ("N1", "рецепт пасты фокачча с розмарином и спаржей", None, None),
    ("N2", "расписание гонок Формула-1 Гран-при Сингапура", None, None),
    ("N3", "покупка акций нейроинтерфейсов и сингулярности на бирже", None, None),
]

CYCLES = 4          # 10 запросов x 4 = 40 замеров
WARMUP = 5          # первых 5 в статистику не входят
TOPK = 5
LINE_TOL = 25       # строка якоря ±tol


def verdict(qid: str, exp_path, exp_line, hits) -> str:
    if exp_path is None:  # пустой контрольный
        top = hits[0][2] if hits else 0.0
        return "чисто" if top < 0.6 else f"polluted(top={top})"
    for p, ln, _ in hits:
        if p == exp_path and (exp_line is None or abs(ln - exp_line) <= LINE_TOL):
            return "РЕЛЕВАНТЕН"
    for p, _, _ in hits:
        if p == exp_path:
            return "ЧАСТИЧНО"
    return "НЕРЕЛЕВАНТЕН"


def main() -> int:
    t0 = time.perf_counter()
    lab9.model()  # холодный старт модели
    cold_start_ms = (time.perf_counter() - t0) * 1000

    _ = lab9.load_snapshot  # снимок хранится у индекса
    if lab9.check_fresh(lab9.connect()):
        print("СТОП: индекс устарел — требуется пересборка", file=sys.stderr)
        return 3

    timings: list[float] = []
    per_query: dict[str, dict] = {}
    n = 0
    for cycle in range(CYCLES):
        for qid, qtext, exp_path, exp_line in SET_A:
            hits, _stale, dt = lab9.query(qtext, TOPK, show_stale=False, quiet=True)
            if n >= WARMUP:
                timings.append(dt)
            prev = per_query.get(qid)
            v = verdict(qid, exp_path, exp_line, hits)
            if prev is None:
                per_query[qid] = {"verdicts": [v], "top": [f"{p}#L{l}" for p, l, _ in hits[:3]]}
            else:
                prev["verdicts"].append(v)
            n += 1
        print(f"# цикл {cycle + 1} готов", file=sys.stderr)

    cold_db = time.perf_counter()
    db = lab9.connect()
    db.close()
    cold_db_ms = (time.perf_counter() - cold_db) * 1000

    rep = {
        "холодный_старт_модели_мс": round(cold_start_ms, 1),
        "загрузка_расширения_мс": round(cold_db_ms, 1),
        "всего_запросов": n,
        "прогрев": WARMUP,
        "в_статистике": len(timings),
        "median_мс": round(statistics.median(timings), 1),
        "mean_мс": round(statistics.mean(timings), 1),
        "p95_мс": round(sorted(timings)[int(len(timings) * 0.95) - 1], 1),
        "max_мс": round(max(timings), 1),
        "вердикты": {k: {"уникальные": sorted(set(v["verdicts"])), "top3": v["top"]}
                     for k, v in per_query.items()},
    }
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

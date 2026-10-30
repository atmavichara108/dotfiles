#!/usr/bin/env python3
"""graph-regen — цикл регенерации графа и горячей памяти (Task 5, мандат ЦУ
graph-hotmem-revive 2026-10-30; корень назван Лабой: граф живёт в
мета-worktree, hotmem молчит 17 суток — нет ЦИКЛА регенерации).

Что делает (раз в час, по образцу session-cop):
1. Прогоняет sessions-coverage (tools/idea-graph/sessions-coverage.mjs,
   zero-LLM) на окне 30 дней — генерит generated/sessions-coverage.json
   в главное дерево волта;
2. Сверяет метрики приёмки Лабы: покрытие (covered/total), свежесть
   (часы с последней регенерации), непокрытые (uncovered как изолированные);
3. Пишет мету-only журнал ~/.local/state/opencode/graph-regen/journal.jsonl.

Приёмка (критерии Лабы): покрытие ≥90% сессий за 30 дней; свежесть ≤24ч;
непокрытые <10%. Красные зоны — телеметрия, не поломка службы (exit 0).
"""
import json
import os
import subprocess
import sys
import time

VAULT = os.path.expanduser("~/Projects/OpenCode-Vault")
COVERAGE = os.path.join(VAULT, "tools/idea-graph/sessions-coverage.mjs")
GEN_JSON = os.path.join(VAULT, "tools/idea-graph/generated/sessions-coverage.json")
STATE = os.path.expanduser("~/.local/state/opencode/graph-regen")
JOURNAL = os.path.join(STATE, "journal.jsonl")
WINDOW_DAYS = 30


def journal(row):
    os.makedirs(STATE, exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    since = time.strftime("%Y-%m-%d", time.gmtime(time.time() - WINDOW_DAYS * 86400))
    now = time.time()
    node = "node"
    if not os.path.exists(COVERAGE):
        print("graph-regen: нет сканера " + COVERAGE)
        return 3
    try:
        subprocess.run([node, COVERAGE, "--since", since],
                       capture_output=True, timeout=180,
                       encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        journal({"ts": int(now), "ok": False, "reason": f"{type(e).__name__}"})
        print(f"graph-regen: прогон не удался ({type(e).__name__})")
        return 0  # телеметрия, не падение службы
    if not os.path.exists(GEN_JSON):
        journal({"ts": int(now), "ok": False, "reason": "no-output"})
        print("graph-regen: сканер не дал вывод")
        return 0
    try:
        d = json.load(open(GEN_JSON, encoding="utf-8"))
        agg = d.get("agg", {})
        # изолированные узлы графа (без рёбер в edges.jsonl) — метрика приёмки
        dg = os.path.join(VAULT, "04-Memory/idea-graph")
        nodes, edged = set(), set()
        try:
            for ln in open(os.path.join(dg, "nodes.jsonl"), encoding="utf-8"):
                try:
                    nodes.add(json.loads(ln)["id"])
                except Exception:  # noqa: BLE001
                    continue
            for ln in open(os.path.join(dg, "edges.jsonl"), encoding="utf-8"):
                try:
                    e = json.loads(ln)
                    for k in ("from", "a", "source", "to", "b", "target"):
                        v = e.get(k)
                        if v:
                            edged.add(v)
                except Exception:  # noqa: BLE001
                    continue
        except OSError:
            pass
        isolated = len(nodes - edged)
        isolated_pct = round(isolated * 100.0 / len(nodes), 1) if nodes else 0.0
        classes = {}
        try:
            for r in d.get("rows", []):
                if r.get("hit"):
                    continue
                classes[r.get("class", "?")] = classes.get(r.get("class", "?"), 0) + 1
        except Exception:  # noqa: BLE001
            pass
        total = int(agg.get("total", 0)) or 1
        covered = int(agg.get("covered", 0))
        uncovered = int(agg.get("uncovered", 0))
        repeat = int(agg.get("repeat_process", 0))
        cov_pct = round(covered * 100.0 / total, 1)
        unc_pct = round(uncovered * 100.0 / total, 1)
        fresh_h = round((now - os.path.getmtime(GEN_JSON)) / 3600.0, 1)
        row = {"ts": int(now), "ok": True, "since": since,
               "total": total, "covered": covered, "uncovered": uncovered,
               "repeat_process": repeat,
               "coverage_pct": cov_pct, "uncovered_pct": unc_pct,
               "uncovered_classes": classes,
               "isolated": isolated, "isolated_pct": isolated_pct,
               "fresh_h": fresh_h,
               "accept": {"coverage_ge_90": cov_pct >= 90,
                          "fresh_le_24h": fresh_h <= 24,
                          "uncovered_lt_10": unc_pct < 10,
                          "isolated_lt_10": isolated_pct < 10},
               "graph_unchanged": d.get("graph_unchanged")}
        journal(row)
        # список дыр (uncovered без hit) — для работы Лабы (карточки-кандидаты)
        holes = [{"id": r.get("id"), "title": r.get("title"),
                  "msgs": r.get("msgs")}
                 for r in d.get("rows", [])
                 if r.get("class") == "uncovered" and not r.get("hit")]
        holes_file = os.path.join(
            VAULT, "tools/idea-graph/generated/holes-ids.txt")
        try:
            with open(holes_file, "w", encoding="utf-8") as f:
                for h in holes:
                    f.write(f"{h['id']}\t{h['msgs']}\t{h['title']}\n")
        except OSError:
            pass
        print("REGEN " + json.dumps(row, ensure_ascii=False))
        return 0
    except Exception as e:  # noqa: BLE001
        journal({"ts": int(now), "ok": False, "reason": f"parse:{type(e).__name__}"})
        print(f"graph-regen: разбор вывода не удался ({type(e).__name__})")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

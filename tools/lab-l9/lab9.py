#!/usr/bin/env python3
"""L9 — локальный семантический индекс памяти (sqlite-vec + e5-small GGUF).

Инференс строго локальный. Индекс производный: vault/.cache/lab-l9/index.sqlite
(gitignored). SSOT — исходники волта; индекс их не переписывает.

Команды:
    lab9.py build                 # пересобрать индекс по allowlist (идемпотентно)
    lab9.py query "<текст>" [-k N]  # ссылки путь#строка + пометка актуальности
    lab9.py check-fresh            # сверить хэш-снимок с текущими источниками
Exit: 0 ok | 3 источник изменился (требуется пересборка) | 2 ошибка.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from corpus import VAULT, corpus_files, sha256  # noqa: E402

CACHE = VAULT / ".cache" / "lab-l9"
DB = CACHE / "index.sqlite"
MODEL = HERE / ".venv" / "models" / "e5-small-hdrrayan-f16.gguf"
DIM = 384
CHUNK_CHARS = 900
MIN_CHUNK = 200

_model = None


def model():
    global _model
    if _model is None:
        from llama_cpp import Llama
        _model = Llama(model_path=str(MODEL), embedding=True, n_threads=4, verbose=False)
    return _model


def embed(text: str, prefix: str) -> list[float]:
    v = model().embed(f"{prefix} {text}")
    n = math.sqrt(sum(a * a for a in v)) or 1.0
    return [a / n for a in v]


def chunks(text: str):
    """Куски по абзацам до CHUNK_CHARS, с номером стартовой строки.

    Куски <MIN_CHUNK символов (шапки-frontmatter) не отдаются отдельно —
    склеиваются со следующим, иначе ведут себя как «магниты» (гипотеза 2).
    """
    lines = text.splitlines()
    cur, start, acc = [], 1, 0
    for i, line in enumerate(lines, 1):
        if acc + len(line) + 1 > CHUNK_CHARS and cur:
            if acc >= MIN_CHUNK or i >= len(lines):
                yield start, "\n".join(cur)
                cur, start, acc = [], i, 0
        cur.append(line)
        acc += len(line) + 1
    if cur:
        yield start, "\n".join(cur)


def raw_embed(text: str, prefix: str) -> list[float]:
    v = model().embed(f"{prefix} {text}")
    return list(v)


def centered(v: list[float], center: list[float]) -> list[float]:
    """Центрирование против центроида корпуса + L2 (правка анизотропии mean-pool)."""
    w = [a - c for a, c in zip(v, center)]
    n = math.sqrt(sum(x * x for x in w)) or 1.0
    return [x / n for x in w]


def embed(text: str, prefix: str) -> list[float]:
    v = raw_embed(text, prefix)
    n = math.sqrt(sum(a * a for a in v)) or 1.0
    return [a / n for a in v]


def ser(v: list[float]) -> bytes:
    import struct
    return struct.pack(f"<{len(v)}f", *v)


def build() -> int:
    files = corpus_files()
    snap = {str(p.relative_to(VAULT)): sha256(p) for p in files}
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = DB.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    import sqlite_vec
    db.enable_load_extension(True)
    sqlite_vec.load(db)
    db.enable_load_extension(False)
    db.execute("create table doc(path text, line integer, text text)")
    db.execute(f"create virtual table vec using vec0(embedding float[{DIM}])")
    t0 = time.perf_counter()
    n = 0
    raws: list[list[float]] = []
    pending: list[tuple[str, int, str]] = []
    for p in files:
        rel = str(p.relative_to(VAULT))
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for start, chunk in chunks(text):
            pending.append((rel, start, chunk))
    # эмбеддинги батчем, центроид = среднее по корпусу (правка анизотропии)
    for rel, start, chunk in pending:
        raws.append(raw_embed(chunk, "passage:"))
    center = [sum(v[i] for v in raws) / len(raws) for i in range(DIM)]
    for (rel, start, chunk), v in zip(pending, raws):
        db.execute("insert into doc values (?,?,?)", (rel, start, chunk))
        db.execute(
            "insert into vec (rowid, embedding) values (?,?)",
            (n, ser(centered(v, center))),
        )
        n += 1
    db.execute("create table meta(k primary key, v)")
    db.execute("insert into meta values ('snapshot', ?)", (json.dumps(snap),))
    db.execute("insert into meta values ('built_at', ?)", (time.strftime("%F %T"),))
    db.execute("insert into meta values ('center', ?)", (json.dumps(center),))
    db.commit()
    db.close()
    tmp.replace(DB)
    print(f"построено чанков: {n}, время: {time.perf_counter() - t0:.1f} с")
    return 0


def load_snapshot(db) -> dict:
    row = db.execute("select v from meta where k='snapshot'").fetchone()
    return json.loads(row[0]) if row else {}


def check_fresh(db, paths: set[str] | None = None) -> list[str]:
    stale = []
    for rel, h in load_snapshot(db).items():
        if paths and rel not in paths:
            continue
        p = VAULT / rel
        try:
            if not p.is_file() or sha256(p) != h:
                stale.append(rel)
        except OSError:
            stale.append(rel)
    return stale


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB)
    if not db.execute("select 1 from pragma_module_list where name='vec0'").fetchone():
        import sqlite_vec
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
    return db


def query(qtext: str, k: int = 5, show_stale: bool = True, quiet: bool = False) -> tuple[list, list, float]:
    if not DB.is_file():
        print("индекс не построен", file=sys.stderr)
        sys.exit(2)
    t0 = time.perf_counter()
    db = connect()
    crow = db.execute("select v from meta where k='center'").fetchone()
    center = json.loads(crow[0]) if crow else [0.0] * DIM
    qv = centered(raw_embed(qtext, "query:"), center)
    rows = db.execute(
        "select d.path, d.line, v.distance from vec v join doc d on d.rowid=v.rowid"
        " where v.embedding match ? and k = ?",
        (ser(qv), k),
    ).fetchall()
    hits = [(p, ln, round(1 - dist / 2, 4)) for p, ln, dist in rows]
    dt = (time.perf_counter() - t0) * 1000
    stale = check_fresh(db, {p for p, _, _ in hits}) if show_stale else []
    if not quiet:
        if stale:
            print(f"[ПОМЕТКА] источник изменился — требуется пересборка: {', '.join(sorted(stale))}")
        for p, ln, sc in hits:
            print(f"{p}#L{ln}  score={sc}")
        print(f"время запроса: {dt:.1f} мс")
    return hits, stale, dt


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "build":
        return build()
    if cmd == "query":
        qtext = sys.argv[2] if len(sys.argv) > 2 else ""
        k = int(sys.argv[sys.argv.index("-k") + 1]) if "-k" in sys.argv else 5
        query(qtext, k, quiet="--json" in sys.argv)
        return 0
    if cmd == "check-fresh":
        if not DB.is_file():
            print("индекс не построен")
            return 2
        db = connect()
        stale = check_fresh(db)
        if stale:
            print("требуется пересборка, изменены:", *sorted(stale), sep="\n  ")
            return 3
        print("индекс актуален")
        return 0
    print("неизвестная команда", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())

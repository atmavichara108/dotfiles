#!/usr/bin/env python3
"""image-read — локальный OCR + text-layout для изображений (Stage 1, T-image-read).

Что делает:
  - распознаёт текст на картинке (tesseract, языки из локальных langpacks
    dotfiles — без системной установки, без root);
  - отдаёт не только текст, но и layout: блоки/строки/слова с координатами
    (x, y, w, h) — где что на изображении (окна, таблицы, блоки ошибок);
  - layout-теги — ЧЕСТНЫЕ эвристики, не ML-детекция: table (выровненные
    колонки слов), terminal (промпт/моноширинная сетка), error
    (ключевые слова error/failed/refused/panic/traceback/denied);
  - FAIL-CLOSED приватность (апрув владельца 2026-10-18): весь выход прогоняется
    через маскирование (e-mail, абсолютные пути, sk-/ghp_/AKIA/Bearer-токены,
    private-key-блоки + точные секреты из ~/.config/opencode/service.json и
    ~/.config/ssa-tg/tg.env); в JSON — поле redactions (тип+счётчик, без
    содержимого). Байты изображения никуда не покидают машину (локальный
    tesseract; внешний vision-слой — Stage 4, отдельно, не включён).

Резолвинг языковых пакетов (порядок, первый годный):
  1. --tessdata DIR           явный;
  2. $IMAGE_READ_TESSDATA     env;
  3. ~/.local/state/image-read/langpacks   (stow-рантайм, если владелец
                                            положил туда);
  4. ~/dotfiles/tools/image-read/langpacks (канон dotfiles, самодостаточный
                                            вариант O1: всё управляется
                                            dotfiles, без root);
  5. системный tessdata (обычно /usr/share/tessdata).
Каталог годен, только если в нём ЕСТЬ ВСЕ запрошенные языки (tesseract не
миксует каталоги). Сбой — чистый отказ с подсказкой (rc=2), без traceback.

Использование:
  python3 image-read.py FILE [--mode text|layout|full] [--json]
                             [--langs eng,rus] [--tessdata DIR]
                             [--max-mb N] [--psm N]
  --mode text    только распознанный текст (маскированный)
  --mode layout  только блоки с координатами и тегами (текст блоков
                 маскирован)
  --mode full    текст + layout + redactions (умолчание)
  --json         вывод как один JSON-объект (default для машинного
                 потребления); --text — человекочитаемый вывод
  --max-mb N     потолок размера файла в МБ (default 15); больше — отказ
  --psm N        tesseract page segmentation mode 0..13 (default 3)
  Вывод-ошибки — rc=1 (аргументы) / rc=2 (среда/tesseract) / rc=3 (файл).

Зависимости: tesseract (системный бинарник — есть), python3 stdlib,
Pillow НЕ нужен (tesseract читает форматы сам). Секреты — только из
config-файлов, никогда из argv.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

DEFAULT_MAX_MB = 15
DEFAULT_LANGS = "eng,rus"
DEFAULT_PSM = 3
ALLOWED_MODES = ("text", "layout", "full")

USAGE = """image-read FILE [--mode text|layout|full] [--json] [--langs eng,rus]
             [--tessdata DIR] [--max-mb N] [--psm N]
Локальный OCR + text-layout (fail-closed приватность, языки из dotfiles).
  --mode text    только распознанный текст (маскированный)
  --mode layout  блоки с координатами (x,y,w,h) и честными эвристик-тегами
                 (table/terminal/error)
  --mode full    текст + layout + redactions (default)
  --json         один JSON-объект (default для машинного потребления)
  --langs L      языки tesseract, разделитель ',' или '+' (default eng,rus)
  --tessdata D   явный каталог .traineddata
  --max-mb N     потолок размера файла в МБ (default 15)
  --psm N        tesseract page segmentation mode 0..13 (default 3)
Каталоги языковых пакетов (первый, где есть ВСЕ запрошенные языки):
  $IMAGE_READ_TESSDATA → ~/.local/state/image-read/langpacks →
  ~/dotfiles/tools/image-read/langpacks → системный tessdata.
Вывод всегда маскирован (e-mail, пути, токены, точные секреты config-файлов).
Коды возврата: 0 ок; 1 аргументы; 2 среда/tesseract; 3 файл."""


# --- фактуры среды ---------------------------------------------------------

def _candidate_tessdata_dirs():
    home = os.path.expanduser("~")
    yield os.path.join(home, ".local", "state", "image-read", "langpacks")
    yield os.path.join(home, "dotfiles", "tools", "image-read", "langpacks")
    # системные (Debian/Ubuntu классика + tesseract 5 дефолт)
    yield "/usr/share/tesseract-ocr/5/tessdata"
    yield "/usr/share/tesseract-ocr/4.00/tessdata"
    yield "/usr/share/tessdata"
    yield "/usr/share/tesseract/tessdata"


def _has_langs(d, langs):
    if not os.path.isdir(d):
        return False
    for lang in langs:
        if not os.path.isfile(os.path.join(d, lang + ".traineddata")):
            return False
    return True


def resolve_tessdata(explicit, langs):
    """Первый годный каталог (все запрошенные языки) или (None, причина)."""
    cands = []
    if explicit:
        cands.append(os.path.expanduser(explicit))
    env_dir = os.environ.get("IMAGE_READ_TESSDATA", "").strip()
    if env_dir:
        cands.append(os.path.expanduser(env_dir))
    cands.extend(_candidate_tessdata_dirs())
    for d in cands:
        if _has_langs(d, langs):
            return d, None
    return None, ("нет каталога tessdata со всеми языками %r; попробуй "
                  "--tessdata DIR или IMAGE_READ_TESSDATA; пакеты живут в "
                  "dotfiles tools/image-read/langpacks/" % ",".join(langs))


# --- маскирование (fail-closed, апрув 2026-10-18) ---------------------------

REDACT = "[REDACTED]"

# (тип, regex). Порядок = приоритет (счётчики независимы, замена однократно).
REDACT_PATTERNS = [
    ("private-key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        re.S)),
    ("api-token", re.compile(
        r"\b(?:sk-[A-Za-z0-9_\-]{8,}|ghp_[A-Za-z0-9]{8,}|gho_[A-Za-z0-9]{8,}"
        r"|github_pat_[A-Za-z0-9_]{8,}|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9\-]{10,})\b")),
    ("bearer", re.compile(
        r"\bBearer\s+[A-Za-z0-9_\-\.=+/]{8,}", re.I)),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    ("abs-path", re.compile(
        r"(?<![\w@.\-/])/(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]+")),
]


def _known_exact_secrets():
    """Точные секреты config-файлов, которые могли попасть на скриншот.

    Читаем только значения (их маскируем), ничего не выводим. Сбой — пусто
    (не блокируем распознавание, паттерны по-прежнему работают).
    """
    secrets = set()
    try:
        with open(os.path.expanduser("~/.config/opencode/service.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        for v in data.values() if isinstance(data, dict) else []:
            if isinstance(v, str) and len(v) >= 8:
                secrets.add(v)
    except Exception:  # noqa: BLE001 — файл может не быть
        pass
    try:
        with open(os.path.expanduser("~/.config/ssa-tg/tg.env"),
                  encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() in ("TG_API_ID", "TG_API_HASH") and len(v) >= 6:
                    secrets.add(v.strip().strip("'\""))
    except Exception:  # noqa: BLE001
        pass
    return {s for s in secrets if len(s) >= 8}


def redact(text, exact_secrets):
    """-> (masked_text, redactions:[{type,count}]). Точные секреты — первыми."""
    counts = {}
    for s in sorted(exact_secrets, key=len, reverse=True):
        n = text.count(s)
        if n:
            text = text.replace(s, REDACT)
            counts["exact-secret"] = counts.get("exact-secret", 0) + n
    for name, rx in REDACT_PATTERNS:
        text, n = rx.subn(REDACT, text)
        if n:
            counts[name] = counts.get(name, 0) + n
    redactions = [{"type": k, "count": v} for k, v in
                  sorted(counts.items(), key=lambda kv: -kv[1])]
    return text, redactions


# --- tesseract -------------------------------------------------------------

ERR_KEYWORDS = ("error", "err ", "failed", "refused", "denied", "panic",
                "traceback", "fatal", "exception", "ошибк", "отказ")
PROMPT_RE = re.compile(r"^(?:[A-Za-z0-9_.\-]+@)?[A-Za-z0-9_.\-]+[:~$#]\s")


def tesseract_version():
    try:
        r = subprocess.run(["tesseract", "--version"], capture_output=True,
                           text=True, timeout=15)
        for line in (r.stdout or r.stderr).splitlines():
            if line.strip():
                return line.strip()
    except Exception:  # noqa: BLE001
        pass
    return ""


def run_tesseract_tsv(path, langs, tessdata_dir, max_mb, psm=DEFAULT_PSM):
    """-> (tsv_text, err). max_mb проверяем ДО вызова (fail-closed)."""
    try:
        size_mb = os.path.getsize(path) / (1024 * 1024)
    except OSError as e:
        return None, "файл не читается: %s" % e
    if size_mb > max_mb:
        return None, ("файл %.1f МБ > потолка %d МБ — отказ (fail-closed; "
                      "повысь --max-mb осознанно)" % (size_mb, max_mb))
    # '+' — канонический разделитель языков tesseract; запятая
    # принимается им за одно имя языка (фикс 2026-10-18, probe-evidence).
    cmd = ["tesseract", path, "stdout", "-l", "+".join(langs),
           "--tessdata-dir", tessdata_dir, "--psm", str(psm), "tsv"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except FileNotFoundError:
        return None, "tesseract не найден в PATH (системный бинарник)"
    except subprocess.TimeoutExpired:
        return None, "tesseract: таймаут 180с (fail-closed)"
    if r.returncode != 0:
        tail = " ".join((r.stderr or "").split())[:300]
        return None, "tesseract rc=%d: %s" % (r.returncode, tail or "без вывода")
    return r.stdout, None


def parse_tsv(tsv_text):
    """TSV tesseract -> words (level 5): [{x,y,w,h,conf,text,block,par,line}]."""
    words = []
    lines = tsv_text.splitlines()
    if not lines:
        return words
    hdr = lines[0].split("\t")
    try:
        idx = {name: hdr.index(name) for name in
               ("level", "block_num", "par_num", "line_num", "left", "top",
                "width", "height", "conf", "text")}
    except ValueError as e:
        raise ValueError("неожиданный TSV-формат tesseract: %s" % e) from e

    def cell(row, i):
        return row[i] if i < len(row) else ""

    for row in lines[1:]:
        cells = row.split("\t")
        if not cells or not cells[idx["level"]]:
            continue
        if cells[idx["level"]] != "5":
            continue
        text = cell(cells, idx["text"]).strip()
        if not text:
            continue
        try:
            conf = float(cell(cells, idx["conf"]) or 0)
            words.append({
                "x": int(float(cell(cells, idx["left"]) or 0)),
                "y": int(float(cell(cells, idx["top"]) or 0)),
                "w": int(float(cell(cells, idx["width"]) or 0)),
                "h": int(float(cell(cells, idx["height"]) or 0)),
                "conf": conf,
                "text": text,
                "block": int(float(cell(cells, idx["block_num"]) or 0)),
                "line": (int(float(cell(cells, idx["line_num"]) or 0)),
                         int(float(cell(cells, idx["par_num"]) or 0))),
            })
        except ValueError:
            continue
    return words


def group_lines(words):
    """Слова -> строки (по (block,par,line_num)):
    {block, text, x, y, w, h, words, avg_conf}."""
    out = []
    groups = {}
    for w in words:
        key = (w["block"], w["line"][0], w["line"][1])
        g = groups.setdefault(key, [])
        g.append(w)
    for key in sorted(groups):
        ws = sorted(groups[key], key=lambda w: w["x"])
        text = " ".join(w["text"] for w in ws)
        out.append({
            "block": key[0],
            "text": text,
            "x": min(w["x"] for w in ws),
            "y": min(w["y"] for w in ws),
            "w": max(w["x"] + w["w"] for w in ws) - min(w["x"] for w in ws),
            "h": max(w["y"] + w["h"] for w in ws) - min(w["y"] for w in ws),
            "words": len(ws),
            "avg_conf": round(sum(w["conf"] for w in ws) / len(ws), 1),
        })
    return out


def _tableish(lines):
    """Честная эвристика: ≥3 строки, ≥2 слова, колонки выровнены по X."""
    if len(lines) < 3:
        return False
    colcount = sum(1 for l in lines if l["words"] >= 2)
    if colcount < 3:
        return False
    # первые x-координаты строк должны сходиться (ступень ≤ 8px от медианы,
    # допуск по высоте каждой строки; фикс 2026-10-18: в py3 переменная
    # comprehension не течёт — прежний l здесь ловил NameError на любых
    # блоках с ≥3 строками по ≥2 слова)
    xs = [l["x"] for l in lines]
    xs_sorted = sorted(xs)
    med = xs_sorted[len(xs_sorted) // 2]
    return sum(1 for l in lines
               if abs(l["x"] - med) <= max(8, l["h"] // 3)) >= colcount


def _terminalish(lines):
    """Честная эвристика: промпт в начале строки (user@host$ / ~$ / #)."""
    return any(PROMPT_RE.match(l["text"]) for l in lines)


def _errorish(text):
    low = text.lower()
    return any(k in low for k in ERR_KEYWORDS)


def build_blocks(words, lines):
    """Блоки (tesseract block_num) с bbox, строками и эвристик-тегами."""
    by_block = {}
    for w in words:
        by_block.setdefault(w["block"], []).append(w)
    lines_by_block = {}
    for l in lines:
        lines_by_block.setdefault(l["block"], []).append(l)
    blocks = []
    for bnum in sorted(by_block):
        ws = by_block[bnum]
        b = {
            "i": bnum,
            "x": min(w["x"] for w in ws),
            "y": min(w["y"] for w in ws),
            "w": max(w["x"] + w["w"] for w in ws) - min(w["x"] for w in ws),
            "h": max(w["y"] + w["h"] for w in ws) - min(w["y"] for w in ws),
            "lines": lines_by_block.get(bnum, []),
            "word_count": len(ws),
            "avg_conf": round(sum(w["conf"] for w in ws) / len(ws), 1),
            "tags": [],
        }
        btext = " ".join(l["text"] for l in b["lines"])
        if _tableish(b["lines"]):
            b["tags"].append("table")
        if _terminalish(b["lines"]):
            b["tags"].append("terminal")
        if _errorish(btext):
            b["tags"].append("error")
        blocks.append(b)
    blocks.sort(key=lambda b: (b["y"], b["x"]))
    return blocks, " ".join(l["text"] for l in lines)


# --- CLI --------------------------------------------------------------------

def parse_args(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)
        return "help"
    file = None
    mode = "full"
    as_json = True  # машинное потребление — дефолт (вывод один JSON)
    langs = DEFAULT_LANGS
    tessdata = ""
    max_mb = DEFAULT_MAX_MB
    psm = DEFAULT_PSM
    # флаги СО значением: значение consumed сразу (i += 2) и не попадает
    # в цикл отдельной итерацией (фикс 2026-10-18: раньше 'FILE --mode
    # full' падало на 'full' как неизвестный аргумент, а '--mode full
    # FILE' принимало 'full' за FILE).
    value_flags = ("--mode", "--langs", "--tessdata", "--max-mb", "--psm")
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in value_flags:
            if i + 1 >= len(argv):
                sys.exit("image-read: %s без значения — отказ (см. --help)" % a)
            val = argv[i + 1]
            if a == "--mode":
                mode = val
            elif a == "--langs":
                langs = val
            elif a == "--tessdata":
                tessdata = val
            elif a == "--psm":
                try:
                    psm = int(val)
                except ValueError:
                    sys.exit("image-read: --psm ожидает целое 0..13, "
                             "получено %r — отказ (см. --help)" % val)
                if not 0 <= psm <= 13:
                    sys.exit("image-read: --psm должен быть 0..13 — отказ "
                             "(см. --help)")
            else:
                try:
                    max_mb = float(val)
                except ValueError:
                    sys.exit("image-read: --max-mb ожидает число, получено"
                             " %r — отказ (см. --help)" % val)
            i += 2
            continue
        if a == "--json":
            as_json = True
        elif a == "--text":
            as_json = False
        elif file is None and not a.startswith("--"):
            file = a
        else:
            sys.exit("image-read: неизвестный аргумент %r — отказ (см. --help)"
                     % a)
        i += 1
    if file is None:
        sys.exit("image-read: нет FILE — отказ (см. --help)")
    if mode not in ALLOWED_MODES:
        sys.exit("image-read: --mode должен быть %s — отказ (см. --help)"
                 % "|".join(ALLOWED_MODES))
    # и ',' и '+' — разделители (CLI-доки — запятая, нативный тул
    # image-read.ts — '+'); в tesseract уходим всегда с '+'.
    lang_list = [x.strip() for x in re.split(r"[,+]", langs) if x.strip()]
    if not lang_list:
        sys.exit("image-read: --langs пуст — отказ (см. --help)")
    if max_mb <= 0:
        sys.exit("image-read: --max-mb должен быть > 0 — отказ")
    return {
        "file": os.path.expanduser(file), "mode": mode, "json": as_json,
        "langs": lang_list, "tessdata": tessdata, "max_mb": max_mb,
        "psm": psm,
    }


def render_human(out):
    """Человекочитаемый вывод (без --json / с --text)."""
    lines = []
    lines.append("file: %s (%d bytes)" % (out["file"], out["size"]))
    lines.append("langs: %s | tessdata: %s | %s"
                 % (",".join(out["langs"]), out["tessdata_dir"],
                    out["tesseract_version"] or "tesseract (версия не ясна)"))
    if out["mode"] in ("text", "full"):
        lines.append("--- text ---")
        lines.append(out["text"] or "(пусто)")
    if out["mode"] in ("layout", "full"):
        lines.append("--- layout ---")
        if not out["blocks"]:
            lines.append("(блоков нет)")
        for b in out["blocks"]:
            tag = (" [" + ",".join(b["tags"]) + "]") if b["tags"] else ""
            lines.append("block %d x=%d y=%d w=%d h=%d conf=%s%s"
                         % (b["i"], b["x"], b["y"], b["w"], b["h"],
                            b["avg_conf"], tag))
            for l in b["lines"]:
                lines.append("    %4d %4d  %s" % (l["x"], l["y"], l["text"]))
    if out["redactions"]:
        lines.append("--- redactions ---")
        for r in out["redactions"]:
            lines.append("  %s: %d" % (r["type"], r["count"]))
    if out["warnings"]:
        lines.append("--- warnings ---")
        lines.extend("  " + w for w in out["warnings"])
    return "\n".join(lines)


def main(argv):
    args = parse_args(argv)
    if args == "help":
        return 0

    if not os.path.isfile(args["file"]):
        sys.exit("image-read: файла нет: %s — отказ (rc=3)" % args["file"])

    tessdata_dir, err = resolve_tessdata(args["tessdata"], args["langs"])
    if tessdata_dir is None:
        sys.exit("image-read: %s — отказ (rc=2)" % err)

    if shutil.which("tesseract") is None:
        sys.exit("image-read: tesseract не найден в PATH — отказ (rc=2)")

    tsv_text, err = run_tesseract_tsv(args["file"], args["langs"],
                                      tessdata_dir, args["max_mb"],
                                      args["psm"])
    if tsv_text is None:
        sys.exit("image-read: %s — отказ (rc=2)" % err)

    warnings = []
    try:
        words = parse_tsv(tsv_text)
    except ValueError as e:
        sys.exit("image-read: %s — отказ (rc=2)" % e)
    if not words:
        warnings.append("tesseract не нашёл слов (пустое изображение или "
                        "языки не подходят)")

    lines = group_lines(words)
    for i, l in enumerate(lines):
        l["_block"] = 0
    # приписываем строки блокам по координатам слова: строка принадлежит
    # блоку её первого слова
    block_of_line = {}
    for w in words:
        key = (w["block"], w["line"][0], w["line"][1])
        if key not in block_of_line:
            block_of_line[key] = w["block"]
    for i, l in enumerate(lines):
        l["_block"] = block_of_line.get(
            (i, l["x"], l["y"]), l.get("_block", 0))
    # точный блок строки: ищем по (block, line_num, par) через words
    # (строки group_lines сгруппированы по этому же ключу — порядок
    # совпадает: и там и тут sort по ключу)
    blocks, full_text = build_blocks(words, lines)

    exact = _known_exact_secrets()
    if full_text:
        masked_text, redactions = redact(full_text, exact)
    else:
        masked_text, redactions = "", []
    # маскируем и текст внутри блоков (layout-режим тоже не утекает)
    for b in blocks:
        for l in b["lines"]:
            l["text"], _ = redact(l["text"], exact)

    size = 0
    try:
        size = os.path.getsize(args["file"])
    except OSError:
        pass

    out = {
        "file": args["file"],
        "size": size,
        "mode": args["mode"],
        "langs": args["langs"],
        "tessdata_dir": tessdata_dir,
        "tesseract_version": tesseract_version(),
        "warnings": warnings,
        "redactions": redactions,
    }
    if args["mode"] in ("text", "full"):
        out["text"] = masked_text
    if args["mode"] in ("layout", "full"):
        out["blocks"] = blocks

    if args["json"]:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(render_human(out))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

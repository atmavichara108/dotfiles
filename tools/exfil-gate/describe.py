#!/usr/bin/env python3
"""describe.py — детерминированное автописание исходящего гейта (приложение 1, мандат СБ).

Требования СБ (письмо ЦУ ic-app1-and-stage4, 2026-11-07):
  - «что/куда/риск» — ТОЛЬКО детерминированный разбор команды: ресурс
    (файл/stdin/пайп), адрес (схема/host:порт), класс + факт;
  - «зачем» — дословно из цели (--goal), не дословно не выдумывается;
  - формат — до четырёх строк с конкретикой, без «передаются данные»;
  - переменный адрес/ресурс — «в переменной X, значение не резолвилось»,
    молча не резолвим и окружение не раскрываем;
  - секретный путь (~/.secrets/**) — называем и БЛОКИРУЕМ до разрешения Ворот
    (один разбор с секрет-сторожем, не два);
  - опасные классы (sudo/rm -rf/systemctl stop/...) — никогда: блок;
  - модель — только в фоне, здесь не используется вообще.

Использование:
  describe.py <cmd> [--goal "цель дословно"]
  describe.py --template "<шаблон со слотами <FILE>>" --slot FILE=/path --slot HOST=host
Коды: 0 — описано; 2 — заблокировано (секрет/опасный класс); 1 — не разобрано.
"""
from __future__ import annotations

import argparse
import os
import re
import sys

NET_CMDS = ("curl", "wget", "ssh", "scp", "rsync", "nc", "ncat")
DANGEROUS = (
    (re.compile(r"(^|[;&|]\s*)sudo\b"), "sudo — повышение привилегий"),
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-?[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-fr\b"), "rm -rf — удаление"),
    (re.compile(r"\bsystemctl\s+(stop|disable|mask)\b"), "systemctl stop/disable/mask"),
    (re.compile(r"\bchmod\b|\bchown\b"), "chmod/chown — права"),
    (re.compile(r"\bmkfs\b|\bshutdown\b|\breboot\b"), "mkfs/shutdown/reboot"),
    (re.compile(r"git\s+push\s+--force|git\s+push\s+-f\b"), "force-push"),
    (re.compile(r"git\s+branch\s+-D\b|git\s+tag\s+-d\b"), "удаление ветки/тега"),
)
SECRET_RE = re.compile(r"(~?/?)\.secrets/")  # secrets-scan:allow (имя содержит secret)
SCHEME_RE = re.compile(r"\b(https?|ftp|sftp|ssh|rsync|file)://([A-Za-z0-9._-]+)(?::(\d{1,5}))?")
USERHOST_RE = re.compile(r"\b([A-Za-z0-9._-]+)@([A-Za-z0-9._-]+)(?=:|\s|$|[\"'])")
HOSTPORT_RE = re.compile(r"\b([A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?):(\d{2,5})\b")
PATH_RE = re.compile(r"(?:^|[\s='\"])((?:~|\.{1,2})?/[\w./-]+)")
SLOT_RE = re.compile(r"<[A-Z][A-Z0-9_]*>")
STDIN_RE = re.compile(r"<\s*([^\s;|&]+)")
VAR_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
PRODUCERS = ("cat", "tar", "gzip", "zip", "jq", "yq", "python", "python3", "head", "tail", "rg", "grep", "awk", "sed", "xxd")

ALLOW_HOSTS_PATH = os.path.expanduser("~/.config/opencode/exfil-allow-hosts.json")


def _split_segments(cmd: str):
    """Сегменты по ; && || — но пайп | сохраняем как поток внутри сегмента."""
    parts = re.split(r"(?:&&|\|\||;)", cmd)
    return [p.strip() for p in parts if p.strip()]


def _dangerous(cmd: str):
    for rx, label in DANGEROUS:
        if rx.search(cmd):
            return label
    return None


def _secret(cmd: str):
    if SECRET_RE.search(cmd):
        m = re.search(r"[^\s'\"]*\.secrets/[^\s'\";|&]*", cmd)
        return m.group(0) if m else "~/.secrets/**"
    return None


def _netcmd(seg: str):
    low = seg.lower()
    for c in NET_CMDS:
        if re.search(rf"(^|[\s;&|]){c}\b", low):
            return c
    return None


def _destination(cmd: str):
    m = SCHEME_RE.search(cmd)
    if m:
        host = m.group(2)
        port = m.group(3) or ("443" if m.group(1) in ("https", "sftp", "ssh") else "80")
        return f"{m.group(1)}://{host}:{port}"
    m = USERHOST_RE.search(cmd)
    if m:
        return f"{m.group(1)}@{m.group(2)} (scp/ssh-цель, порт по умолчанию 22)"
    m = HOSTPORT_RE.search(cmd)
    if m and not m.group(1).startswith("/"):
        return f"{m.group(1)}:{m.group(3)}"
    return None


def _resources(cmd: str):
    out = []
    for m in PATH_RE.finditer(cmd):
        p = m.group(1)
        if p.startswith(("/usr", "/bin", "/etc")) and len(p.split("/")) <= 3:
            continue  # системный путь исполнения, не ресурс
        out.append(p)
    m = STDIN_RE.search(cmd)
    if m:
        out.append(f"stdin<{m.group(1)}")
    return out


def _producer(seg: str):
    for p in PRODUCERS:
        if re.search(rf"(^|[\s;&|]){p}\b", seg.lower()):
            return p
    return None


def _vars(cmd: str):
    return sorted(set(VAR_RE.findall(cmd)))


def _allow_hosts():
    try:
        import json
        if os.path.exists(ALLOW_HOSTS_PATH):
            return set(json.load(open(ALLOW_HOSTS_PATH, encoding="utf-8")).get("hosts", []))
    except Exception:  # noqa: BLE001
        pass
    return set()


def describe(cmd: str, goal: str = ""):
    """→ (lines, exit_code). lines ≤4; exit 2 = блок, 0 = описано, 1 = не разобрано."""
    dang = _dangerous(cmd)
    if dang:
        return [f"БЛОК: опасный класс в команде — {dang}. Автоописание гейта для "
                f"опасных классов не выдаётся никогда (требование СБ)."], 2
    secret = _secret(cmd)  # secrets-scan:allow (имя содержит secret)
    if secret:
        return [f"БЛОК: секретный путь «{secret}» — данные Ворот не уходят в сеть "
                f"и не описываются для гейта до разрешения секретов (owner-gate ask_secret)."], 2

    segs = _split_segments(cmd)
    # Нераскрытый слот <SLOT> в команде = проверяется не та команда, что
    # исполнится (дефект СБ sb-describe-failopen-defect): блок.
    slot_left = sorted(set(SLOT_RE.findall(cmd)))
    if slot_left:
        return [f"БЛОК: нераскрытый слот {', '.join(slot_left)} — команда с "
                f"неподставленным слотом не идёт в гейт (fail-closed)."], 2

    nets = [(s, _netcmd(s)) for s in segs]
    nets = [(s, c) for s, c in nets if c]
    if not nets:
        return ["НЕ РАЗОБРАНО: исходящая сетевая команда не опознана."], 1

    lines = []
    what, where = [], []
    unknown = []
    for seg, net in nets:
        dest = _destination(seg)
        seg_vars = _vars(seg)
        if "|" in seg:
            prod = _producer(seg.split("|", 1)[0])
            if not prod:
                unknown.append("неизвестный производитель пайпа")
                what.append("пайп: производитель не распознан")
            else:
                what.append(f"пайп: поток от «{prod}» через {net}")
        if dest:
            where.append(f"{dest} (через {net})")
        elif seg_vars:
            # Переменный адрес — заявленный эталон (СБ): честно назвать, не резолвить.
            where.append(f"адрес в переменной {', '.join(seg_vars)}, "
                         f"значение не резолвилось (через {net})")
        else:
            unknown.append(f"адрес не распознан для «{net}»")
            where.append(f"адрес не распознан (через {net})")
        if "|" not in seg:
            res = _resources(seg)
            if res:
                what.append("ресурс: " + ", ".join(res))
            else:
                what.append(f"уход без файла: {net} без аргумента-ресурса — уходит "
                            f"stdout/параметры URL")
    if unknown:
        # Fail-closed (требование СБ): неизвестный адрес/источник не трактуется
        # как локальный — гейт не пропускает.
        return ["БЛОК: адрес/источник не распознан — гейт не пропускает "
                f"неизвестный адрес: {'; '.join(dict.fromkeys(unknown))}. "
                f"Дай конкретный адрес или разрешённый слот."], 2
    lines.append("ЧТО: " + "; ".join(dict.fromkeys(what)))
    lines.append("КУДА: " + "; ".join(dict.fromkeys(where)))

    allow = _allow_hosts()
    ext = []
    var_addr = False
    for w in where:
        if "в переменной" in w or "не распознан" in w:
            var_addr = True
        m = re.search(r"//([A-Za-z0-9._-]+)|@([A-Za-z0-9._-]+)", w)
        host = (m.group(1) or m.group(2)) if m else None
        if host and host not in ("127.0.0.1", "localhost", "::1") and host not in allow:
            ext.append(host)
    if ext:
        lines.append("РИСК: внешний адрес вне списка разрешённых — "
                     + ", ".join(sorted(set(ext)))
                     + " (exfil-класс: данные покидают хост)")
    elif var_addr:
        lines.append("РИСК: адрес в переменной/не резолвился — выход за хост "
                     "исключить нельзя, exfil-класс НЕ снимается")
    else:
        lines.append("РИСК: адрес локальный/разрешённый — утечка вне хоста не следует из разбора")
    vars_ = _vars(cmd)
    if vars_:
        names = ", ".join(vars_)
        lines.append(f"ПЕРЕМЕННЫЕ: {names} — адрес/ресурс в переменной, "
                     f"значение не резолвилось (молча не раскрываем)")
    if goal:
        lines.append(f"ЗАЧЕМ: {goal.strip()}")
    while len(lines) > 4:
        lines.pop()
    return lines, 0


def render_and_describe(cmd: str, goal: str, template: str, slots: dict):
    """Ступень 4: подстановка слотов проходит ТОТ же разбор, что и полная команда.

    Строже прямой команды там, где ЦУ выставил условие: внешний адрес вне
    списка разрешённых — БЛОК (слоты не обходят классификатор).
    """
    if not template:
        return describe(cmd, goal)
    rendered = template
    for k, v in slots.items():
        rendered = rendered.replace(f"<{k}>", v).replace(f"{{{k}}}", v)
    left = set(VAR_RE.findall(rendered)) - set(slots)
    if left:
        return [f"БЛОК: в шаблоне остались неподставленные слоты: "
                + ", ".join(sorted(left)) + " — не резолвим молча."], 2
    lines, code = describe(rendered, goal)
    if code != 0:
        return lines, code
    allow = _allow_hosts()
    for w in lines:
        if not w.startswith("КУДА:"):
            continue
        for m in re.finditer(r"//([A-Za-z0-9._-]+)|@([A-Za-z0-9._-]+)", w):
            host = m.group(1) or m.group(2)
            if host and host not in ("127.0.0.1", "localhost", "::1") and host not in allow:
                return [f"БЛОК: внешний адрес вне списка разрешённых — {host}. "
                        f"Слоты не обходят риск-гейт (условие ступени 4). "
                        f"Легит: добавь хост в ~/.config/opencode/exfil-allow-hosts.json "
                        f"или иди полной командой через ask-гейт."], 2
    return lines, code


def main():
    ap = argparse.ArgumentParser(prog="describe")
    ap.add_argument("cmd", nargs="?", default="")
    ap.add_argument("--goal", default="")
    ap.add_argument("--template", default="")
    ap.add_argument("--slot", action="append", default=[], help="k=v (повторяемо)")
    a = ap.parse_args()
    slots = {}
    for s in a.slot:
        if "=" not in s:
            print("describe: --slot в форме k=v", file=sys.stderr)
            return 1
        k, v = s.split("=", 1)
        slots[k.strip()] = v.strip()
    if not a.cmd and not a.template:
        print("usage: describe.py <cmd|--template tpl> [--goal 'цель'] [--slot k=v]", file=sys.stderr)
        return 1
    lines, code = render_and_describe(a.cmd, a.goal, a.template, slots)
    for ln in lines:
        print(ln)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

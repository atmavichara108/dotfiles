#!/usr/bin/env python3
"""Проверка и починка YAML-фронтматера в markdown-файлах (Obsidian-канон).

Причина класса «Obsidian показывает --- блок как текст»:
  1) невалидный YAML — чаще всего двоеточие внутри незакавыченного значения:
        title: Почтовый стек: исследование      # YAML-ошибка
        title: "Почтовый стек: исследование"    # валидно
  2) блок --- не на первой строке (пустая строка или заголовок перед ним).

Режимы:
    fm.py lint <dir>        — список битых файлов + класс/причина
    fm.py fix <dir> [--dry] — починить (идемпотентно, тело файла не трогается)
    fm.py check <file>      — проверить один файл (rc=0 валиден)

Только stdlib + PyYAML. Без сети. Не трогает .git/node_modules/.obsidian.
"""
import os
import re
import sys

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("нужен PyYAML: python3 -m pip install --user pyyaml")

SKIP_DIRS = {'.git', 'node_modules', '.obsidian', '.cache', '.meta-worktrees'}
KEY_RE = re.compile(r'^([A-Za-z_][\w.-]*):[ \t]*(.*)$')
PLAIN_SPECIAL = tuple('[]{},&*#|>!%@`"\'')
SCAN_LINES = 12   # где искать «съехавший» блок
MAX_PREFIX_LINES = 8


def split_fm(text):
    """Фронтматер ровно с первой строки -> (fm, body) или (None, text)."""
    if not text.startswith('---'):
        return None, text
    nl = text.find('\n')
    if nl < 0:
        return None, text
    end = text.find('\n---', 3)
    if end < 0:
        return None, text
    return text[nl + 1:end], text[end + len('\n---'):]


def displaced(text):
    """Блок --- не на первой строке -> (fm, prefix, rest) или None.

    prefix — то, что стояло перед блоком (пустые строки/заголовок),
    rest — содержимое после закрывающего ---.

    Отсекаем ложные срабатывания: `---` как горизонтальная линия в обычном
    документе (перед ним проза, блок не парсится как mapping).
    """
    if text.startswith('---'):
        return None
    lines = text.split('\n')
    for i in range(1, min(SCAN_LINES, len(lines))):
        if lines[i].strip() != '---':
            continue
        # перед блоком допустимы только пустые строки и markdown-заголовки
        pre = lines[:i]
        if any(l.strip() and not l.lstrip().startswith('#') for l in pre):
            continue
        for j in range(i + 1, min(i + 120, len(lines))):
            if lines[j].strip() == '---':
                block = '\n'.join(lines[i + 1:j])
                try:
                    ok = isinstance(yaml.safe_load(block), dict)
                except Exception:
                    ok = False
                if not ok:
                    # битый YAML-блок тоже считаем фронтматером, если он
                    # начинается с ключа вида `name:` (иначе это не блок)
                    first = next((l for l in block.split('\n') if l.strip()), '')
                    ok = bool(KEY_RE.match(first))
                if not ok:
                    continue
                prefix = '\n'.join(pre).strip('\n')
                rest = '\n'.join(lines[j + 1:])
                return block, prefix, rest
        continue
    return None


def parse(fm):
    d = yaml.safe_load(fm)
    if not isinstance(d, dict):
        raise ValueError('фронтматер не является YAML-mapping')
    return d


def needs_quote(val):
    """Нужно ли закавычить plain-значение, чтобы YAML его понял."""
    v = val.strip()
    if not v:
        return False
    if v[0] in ('"', "'", '[', '{', '|', '>'):
        return False
    if ': ' in v or v.endswith(':'):
        return True
    if ' #' in v:
        return True
    if v[0] in PLAIN_SPECIAL:
        return True
    return False


def quoted(val):
    v = val.strip()
    return '"' + v.replace('\\', '\\\\').replace('"', '\\"') + '"'


def quoted_list(val):
    """`"a", "b"` -> `["a", "b"]` (потерянный YAML-список). Иначе None."""
    v = val.strip()
    if not (v.startswith('"') and v.endswith('"') and '",' in v):
        return None
    parts = re.split(r'",\s*"', v)
    items = []
    for idx, p in enumerate(parts):
        if idx == 0:
            p = p[1:]
        if idx == len(parts) - 1:
            p = p[:-1]
        items.append(quoted(p))
    return '[' + ', '.join(items) + ']'


def scalar_ok(val):
    """Разбирается ли значение как отдельный YAML-скаляр."""
    try:
        yaml.safe_load('k: ' + val.strip())
        return True
    except Exception:
        return False


def fix_values(fm):
    """Закавычить проблемные значения. -> (новый fm, число правок)."""
    lines = fm.split('\n')
    changed = 0
    for i, line in enumerate(lines):
        m = KEY_RE.match(line)
        if not m:
            continue  # вложенные строки/списки не трогаем
        key, val = m.group(1), m.group(2)
        lst = quoted_list(val)
        if lst is not None:
            lines[i] = f'{key}: {lst}'
            changed += 1
        elif needs_quote(val):
            lines[i] = f'{key}: {quoted(val)}'
            changed += 1
    new_fm = '\n'.join(lines)
    try:
        parse(new_fm)
        return new_fm, changed
    except Exception:
        pass
    lines2 = new_fm.split('\n')
    for i, line in enumerate(lines2):
        m = KEY_RE.match(line)
        if not m:
            continue
        key, val = m.group(1), m.group(2)
        if val.strip() and not scalar_ok(val):
            lines2[i] = f'{key}: {quoted(val)}'
            changed += 1
    return '\n'.join(lines2), changed


def fix_text(text):
    """Починить файл. Возвращает (новый текст, число правок, ошибка|None)."""
    fm, body = split_fm(text)
    if fm is not None:
        try:
            parse(fm)
            return text, 0, None
        except Exception:
            pass
        new_fm, changed = fix_values(fm)
        try:
            parse(new_fm)
        except Exception as e:
            return text, changed, str(e).split('\n')[0]
        return '---\n' + new_fm + '\n---' + body, changed, None

    dis = displaced(text)
    if dis is None:
        return text, 0, 'фронтматера нет (или он не закрыт)'
    fm, prefix, rest = dis
    new_fm, changed = fix_values(fm)
    try:
        parse(new_fm)
    except Exception as e:
        return text, changed, str(e).split('\n')[0]
    head = '---\n' + new_fm + '\n---\n'
    mid = (prefix.strip('\n') + '\n\n') if prefix.strip() else ''
    tail = rest.lstrip('\n')
    return head + mid + tail, changed + 1, None


def diagnose(text):
    """-> (класс, причина|None). класс: ok / yaml / displaced / none."""
    fm, _ = split_fm(text)
    if fm is not None:
        try:
            parse(fm)
            return 'ok', None
        except Exception as e:
            return 'yaml', str(e).split('\n')[0]
    dis = displaced(text)
    if dis is not None:
        return 'displaced', 'блок --- не на первой строке'
    return 'none', None


def walk(root):
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in sorted(fns):
            if fn.endswith('.md'):
                yield os.path.join(dp, fn)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    mode, target = sys.argv[1], sys.argv[2]
    dry = '--dry' in sys.argv
    if mode == 'check':
        text = open(target, encoding='utf-8-sig').read()
        kind, reason = diagnose(text)
        print({'ok': 'OK', 'yaml': 'BROKEN-YAML', 'displaced': 'NOT-AT-TOP',
               'none': 'NO-FRONTMATTER'}[kind] + (': ' + reason if reason else ''))
        return 0 if kind == 'ok' else 1

    files = [target] if os.path.isfile(target) else list(walk(target))
    stats = {'yaml': 0, 'displaced': 0}
    fixed = unfixable = 0
    for p in files:
        try:
            text = open(p, encoding='utf-8-sig').read()
        except Exception as e:
            print('READ-ERR', p, e)
            continue
        kind, reason = diagnose(text)
        if kind in ('ok', 'none'):
            continue
        stats[kind] += 1
        if mode == 'lint':
            print(f'{kind}\t{p}\t{reason}')
            continue
        new, n, err = fix_text(text)
        if err:
            unfixable += 1
            print(f'UNFIXABLE\t{p}\t{err}')
            continue
        if not dry:
            with open(p, 'w', encoding='utf-8') as f:
                f.write(new)
        fixed += 1
    print(f'\nИТОГО: битый YAML {stats["yaml"]}, не на первой строке {stats["displaced"]},'
          f' починено {fixed}, непочиняемых {unfixable}'
          f'{" (dry-run, файлы не тронуты)" if dry else ""}')


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""tg-upload — fail-closed отправка ФАЙЛОВ (документами) в рабочую группу SSA.

Дополняет мост: tg-send (текст) и tg-attach (приём вложений) не умеют
отправлять файлы — этот скрипт закрывает дыру. Никаких обходов каталогов
и глобов: только явные пути файлов аргументами.

Жёсткие рамки (owner scope, письмо координатора letter-upload-capability,
2026-10-14):
  - --topic ID обязателен; разрешён ровно topic 33 («Тэсты»);
  - получатель ТОЛЬКО SSA_GROUP_ID из env (whitelist, переопределения нет);
  - сессия только владельца (как tg-edit: чужая сессия — отказ);
  - размер: жёсткий лимит 2 ГиБ на файл (лимит Telethon); практический
    порог 100 МиБ — свыше предупреждение (согласовывай большие файлы);
  - секретоподобные имена файлов (.pem/.key/.env/id_rsa/…) — отказ
    ДО отправки, симметрично tg-attach;
  - двухфазность: ВСЕ файлы проверены ДО первой отправки; провал любой
    проверки — ноль отправок;
  - --dry-run: полная проверка (env, сессия, топик, файлы) без send_file;
  - после каждой успешной отправки печатается message_id.

Секреты только из ~/.config/ssa-tg/tg.env, никогда из аргументов/репо.
Запуск: python3 tg-upload.py [--dry-run] --topic 33 FILE [FILE ...]
  (exec-бит ставит владелец: chmod +x — вне зоны агента).

Зависимость: telethon (системно, ставит владелец: pip install --user telethon).
"""
import os
import sys
import asyncio

ENV_FILE = os.path.expanduser("~/.config/ssa-tg/tg.env")
SESSION = os.path.expanduser("~/.local/state/ssa-tg/ssa.session")

ALLOWED_TOPICS = {33}
OWNER_USERNAME = "atma_vichara108"  # как tg-edit: чужая сессия — отказ
HARD_MAX_BYTES = 2 * 1024**3          # 2 ГиБ — жёсткий лимит Telethon
PRACTICAL_WARN_BYTES = 100 * 1024**2  # практический порог: предупреждение

SECRET_HINTS = (".pem", ".key", ".env", "id_rsa", "private", ".pfx", ".p12",
                "credentials", "secret")

USAGE = """tg-upload --topic 33 [--dry-run] FILE [FILE ...]
  --topic 33   ID форумного топика (обязателен; разрешён ровно 33,
               другое — отказ без чтения группы)
  --dry-run    полная проверка (env/сессия/топик/файлы) без отправки
  FILE         явные пути файлов (один или несколько); каталоги и глобы
               не принимаются — только существующие обычные файлы
Размер: жёсткий лимит 2 ГиБ на файл (лимит Telethon); практический порог
100 МиБ — свыше печатается предупреждение (большие файлы согласовывай).
Получатель всегда один — группа SSA из env (whitelist, не меняется).
После успешной отправки печатает message_id каждого файла."""


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env


def parse_proxy(url):
    """socks5://host:port -> кортеж для telethon. Пусто -> None (прямое)."""
    url = (url or "").strip()
    if not url:
        return None
    scheme, _, rest = url.partition("://")
    host, _, port = rest.partition(":")
    return (scheme or "socks5", host, int(port or "1080"))


def looks_secret(name):
    blob = name.lower()
    return any(h in blob for h in SECRET_HINTS)


def main(argv):
    if "--help" in argv or "-h" in argv:
        print(USAGE)  # безвредно: до env, сети и файлов не доходим
        return
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    topic = None
    known_vals = set()
    if "--topic" in argv:
        i = argv.index("--topic")
        if i + 1 >= len(argv):
            sys.exit("tg-upload: --topic требует значение (ID) — отказ")
        try:
            topic = int(argv[i + 1])
        except ValueError:
            sys.exit("tg-upload: --topic требует целое число — отказ")
        known_vals.add(argv[i + 1])
    rest = [a for a in argv if a != "--topic"]
    files = [a for a in rest if a not in known_vals]
    stray = [a for a in files if a.startswith("--")]
    if stray:
        sys.exit(f"tg-upload: неизвестные флаги {stray} — отказ (см. --help)")
    if topic is None:
        sys.exit("tg-upload: нет --topic ID — отправка запрещена "
                 "(fail-closed; см. --help)")
    if topic not in ALLOWED_TOPICS:
        sys.exit(f"tg-upload: topic {topic} вне разрешённого scope "
                 f"(разрешён: {sorted(ALLOWED_TOPICS)}) — отказ")
    if not files:
        sys.exit("tg-upload: нет файлов — указывай явные пути (см. --help)")

    # Фаза 1: проверить ВСЕ файлы до единой отправки.
    plan = []
    seen = set()
    total = 0
    for raw in files:
        real = os.path.realpath(raw)
        base = os.path.basename(real)
        if looks_secret(base):
            sys.exit(f"tg-upload: {base} выглядит секретоподобно "
                     f"{SECRET_HINTS} — отказ, ноль отправок")
        if real in seen:
            sys.exit(f"tg-upload: дубликат файла: {raw} — отказ, ноль отправок")
        seen.add(real)
        if not os.path.exists(real):
            sys.exit(f"tg-upload: файл не найден: {raw} — отказ, ноль отправок")
        if not os.path.isfile(real):
            sys.exit(f"tg-upload: не обычный файл (каталог?): {raw} — только "
                     "явные пути файлов, без глобов — отказ, ноль отправок")
        if not os.access(real, os.R_OK):
            sys.exit(f"tg-upload: нет права чтения: {raw} — отказ, "
                     "ноль отправок")
        size = os.path.getsize(real)
        if size <= 0:
            sys.exit(f"tg-upload: пустой файл: {raw} — отказ, ноль отправок")
        if size > HARD_MAX_BYTES:
            sys.exit(f"tg-upload: {base} {size} байт свыше жёсткого лимита "
                     f"{HARD_MAX_BYTES} байт (2 ГиБ, Telethon) — отказ, "
                     "ноль отправок")
        if size > PRACTICAL_WARN_BYTES:
            sys.stderr.write(f"tg-upload: предупреждение: {base} свыше "
                             f"практического порога {PRACTICAL_WARN_BYTES} "
                             "байт (100 МиБ) — продолжаю\n")
        plan.append((real, base, size))
        total += size

    env = load_env(ENV_FILE)
    api_id = env.get("TG_API_ID", "")
    api_hash = env.get("TG_API_HASH", "")
    group = env.get("SSA_GROUP_ID", "")
    proxy = parse_proxy(env.get("TG_PROXY", ""))
    if not api_id or not api_hash or not group:
        sys.exit("tg-upload: заполни TG_API_ID/TG_API_HASH/SSA_GROUP_ID в "
                 + ENV_FILE)
    try:
        from telethon import TelegramClient
    except ImportError:
        sys.exit("tg-upload: нет telethon (владелец ставит: "
                 "pip install --user telethon)")
    try:
        import python_socks  # noqa: F401  (нужен telethon для TG_PROXY)
    except ImportError:
        if proxy is not None:
            sys.exit("tg-upload: задан TG_PROXY, но нет python-socks "
                     "(владелец ставит: pip install --user "
                     "'python-socks[asyncio]')")

    async def run():
        async with TelegramClient(SESSION, int(api_id), api_hash,
                                  proxy=proxy) as client:
            me = await client.get_me()
            if (me.username or "").lower() != OWNER_USERNAME:
                sys.exit(f"tg-upload: сессия не владельца "
                         f"(ожидался {OWNER_USERNAME}) — отказ")
            ent = await client.get_entity(int(group))
            topics = await _topic_ids(client, ent)
            if topic not in topics:
                sys.exit(f"tg-upload: топика {topic} нет в группе "
                         f"(есть: {sorted(topics)}) — отказ")
            if dry:
                print(f"dry-run -> chat {group} topic={topic}: "
                      f"{len(plan)} файл(ов), {total} байт")
                for real, base, size in plan:
                    print(f"  [file] {base} ({size} байт) <- {real}")
                print("dry-run: отправок не было (send_file не вызывался)")
                sys.stderr.write(f"tg-upload: dry-run, файлов={len(plan)}, "
                                 "отправок не было\n")
                return
            sys.stderr.write(f"tg-upload: как {me.username or me.id} -> "
                             f"{group} topic={topic}\n")
            sent = []
            # Фаза 2: отправлять по одному; провал — стоп с отчётом об
            # уже отправленных message_id.
            for real, base, size in plan:
                try:
                    msg = await client.send_file(ent, real, reply_to=topic,
                                                 force_document=True)
                except Exception as e:  # noqa: BLE001
                    done = ", ".join(str(i) for i in sent) or "нет"
                    sys.exit(f"tg-upload: провал на {base} "
                             f"({type(e).__name__}: {e}); успешно "
                             f"отправлены message_id: {done} — стоп")
                mid = getattr(msg, "id", None)
                if mid is None:
                    done = ", ".join(str(i) for i in sent) or "нет"
                    sys.exit(f"tg-upload: send_file вернул объект без "
                             f"message_id ({type(msg).__name__}); успешно "
                             f"отправлены message_id: {done} — стоп")
                sent.append(mid)
                print(f"tg-upload: ok message_id={mid} topic={topic} "
                      f"file={base}")
            sys.stderr.write(f"tg-upload: topic={topic} "
                             f"файлов={len(sent)}\n")

    asyncio.run(run())


async def _topic_ids(client, entity):
    """ID существующих топиков (только метаданные заголовков, без текстов)."""
    from telethon.tl.functions.messages import GetForumTopicsRequest
    r = await client(GetForumTopicsRequest(
        peer=entity, offset_date=None, offset_id=0, offset_topic=0, limit=100))
    return {t.id for t in r.topics}


if __name__ == "__main__":
    main(sys.argv[1:])

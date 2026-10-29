#!/usr/bin/env python3
"""portal-tg-send — отправка в кабинет Капитанский портал (весь чат (chat-scope)) = tg-send с TG_PROFILE=portal.

Обёртка не дублирует логику: единственный источник — scripts/.local/bin/tg-send.py
+ профиль dv (~/.config/portal-tg/tg.env, ~/.local/state/portal-tg/dv.session,
DV_GROUP_ID, ALLOWED_TOPICS={}, журнал ~/.local/state/portal-tg/journal.jsonl).
SSA-профиль неизменен (умолчание без TG_PROFILE). Мандат portal-tg-gateway.
"""
import os
import sys

os.environ["TG_PROFILE"] = "portal"  # ДО запуска целевого скрипта

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-send.py")] + sys.argv[1:])

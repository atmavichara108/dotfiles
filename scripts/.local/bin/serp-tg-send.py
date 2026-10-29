#!/usr/bin/env python3
"""serp-tg-send — отправка в кабинет SERPlux (топик 186) = tg-send с TG_PROFILE=serp.

Обёртка не дублирует логику: единственный источник — scripts/.local/bin/tg-send.py
+ профиль dv (~/.config/serp-tg/tg.env, ~/.local/state/serp-tg/dv.session,
DV_GROUP_ID, ALLOWED_TOPICS={186}, журнал ~/.local/state/serp-tg/journal.jsonl).
SSA-профиль неизменен (умолчание без TG_PROFILE). Мандат serp-tg-gateway.
"""
import os
import sys

os.environ["TG_PROFILE"] = "serp"  # ДО запуска целевого скрипта

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-send.py")] + sys.argv[1:])

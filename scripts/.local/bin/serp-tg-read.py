#!/usr/bin/env python3
"""serp-tg-read — чтение кабинета SERPlux (топик 186) = tg-read с TG_PROFILE=serp.

Обёртка не дублирует логику: единственный источник — scripts/.local/bin/tg-read.py
+ профиль dv (~/.config/serp-tg/tg.env, ~/.local/state/serp-tg/dv.session,
DV_GROUP_ID, read-scope={186}, журнал ~/.local/state/serp-tg/journal.jsonl).
SSA-профиль неизменен (умолчание без TG_PROFILE). Мандат serp-tg-gateway.
"""
import os
import sys

os.environ["TG_PROFILE"] = "serp"  # ДО запуска целевого скрипта

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-read.py")] + sys.argv[1:])

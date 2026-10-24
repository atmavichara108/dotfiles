#!/usr/bin/env python3
"""dv-tg-read — чтение кабинета dv-hub (топик 1399) = tg-read с TG_PROFILE=dv.

Обёртка не дублирует логику: единственный источник — scripts/.local/bin/tg-read.py
+ профиль dv (~/.config/dv-tg/tg.env, ~/.local/state/dv-tg/dv.session,
DV_GROUP_ID, read-scope={1399}, журнал ~/.local/state/dv-tg/journal.jsonl).
SSA-профиль неизменен (умолчание без TG_PROFILE). Мандат dv-tg-gateway.
"""
import os
import sys

os.environ["TG_PROFILE"] = "dv"  # ДО запуска целевого скрипта

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-read.py")] + sys.argv[1:])

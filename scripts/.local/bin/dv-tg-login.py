#!/usr/bin/env python3
"""dv-tg-login — интерактивный вход владельца в кабинет dv-hub = tg-login с
TG_PROFILE=dv. Код из Telegram вводит ВЛАДЕЛЕЦ (агент stdin не имеет).

Обёртка не дублирует логику: единственный источник — scripts/.local/bin/tg-login.py
+ профиль dv (~/.config/dv-tg/tg.env, ~/.local/state/dv-tg/dv.session).
SSA-профиль неизменен (умолчание без TG_PROFILE). Мандат dv-tg-gateway.
"""
import os
import sys

os.environ["TG_PROFILE"] = "dv"  # ДО запуска целевого скрипта

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-login.py")] + sys.argv[1:])

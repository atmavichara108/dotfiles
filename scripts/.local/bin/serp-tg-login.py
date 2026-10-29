#!/usr/bin/env python3
"""serp-tg-login — интерактивный вход владельца в кабинет SERPlux = tg-login с
TG_PROFILE=serp. Код из Telegram вводит ВЛАДЕЛЕЦ (агент stdin не имеет).

Обёртка не дублирует логику: единственный источник — scripts/.local/bin/tg-login.py
+ профиль dv (~/.config/serp-tg/tg.env, ~/.local/state/serp-tg/dv.session).
SSA-профиль неизменен (умолчание без TG_PROFILE). Мандат serp-tg-gateway.
"""
import os
import sys

os.environ["TG_PROFILE"] = "serp"  # ДО запуска целевого скрипта

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-login.py")] + sys.argv[1:])

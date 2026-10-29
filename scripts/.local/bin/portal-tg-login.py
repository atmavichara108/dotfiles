#!/usr/bin/env python3
"""portal-tg-login — интерактивный вход владельца в кабинет Капитанский портал = tg-login с
TG_PROFILE=portal. Код из Telegram вводит ВЛАДЕЛЕЦ (агент stdin не имеет).

Обёртка не дублирует логику: единственный источник — scripts/.local/bin/tg-login.py
+ профиль dv (~/.config/portal-tg/tg.env, ~/.local/state/portal-tg/dv.session).
SSA-профиль неизменен (умолчание без TG_PROFILE). Мандат portal-tg-gateway.
"""
import os
import sys

os.environ["TG_PROFILE"] = "portal"  # ДО запуска целевого скрипта

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-login.py")] + sys.argv[1:])

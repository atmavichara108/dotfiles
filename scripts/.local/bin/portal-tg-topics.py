#!/usr/bin/env python3
"""portal-tg-topics — топики кабинета портала = tg-topics с TG_PROFILE=portal.

ВАЖНО (урок portal-formalities, ЦУ 2026-10-29): зови по НАСТОЯЩЕМУ пути
~/dotfiles/scripts/.local/bin/portal-tg-topics.py — через симлинк ~/.local/bin
HERE-резолв уводит в каталог симлинка. Same для прочих execv-обёрток.
"""
import os
import sys

os.environ["TG_PROFILE"] = "portal"

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-topics.py")] + sys.argv[1:])

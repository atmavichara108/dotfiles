#!/usr/bin/env python3
"""portal-tg-topics — топики кабинета портала = tg-topics с TG_PROFILE=portal."""
import os
import sys

os.environ["TG_PROFILE"] = "portal"

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(sys.executable, [sys.executable, os.path.join(HERE, "tg-topics.py")] + sys.argv[1:])

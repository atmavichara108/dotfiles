import json
import os

def load_wal_colors():
    """Читает палитру pywal из кэша. Fallback на DoomOne если кэша нет."""
    wal_cache = os.path.expanduser("~/.cache/wal/colors.json")

    # Fallback палитра
    fallback = [
        ["#282c34", "#282c34"],  # bg
        ["#bbc2cf", "#bbc2cf"],  # fg
        ["#1c1f24", "#1c1f24"],  # color01
        ["#ff6c6b", "#ff6c6b"],  # color02
        ["#98be65", "#98be65"],  # color03
        ["#da8548", "#da8548"],  # color04
        ["#51afef", "#51afef"],  # color05
        ["#c678dd", "#c678dd"],  # color06
        ["#46d9ff", "#46d9ff"],  # color07
        ["#7d7d7d", "#7d7d7d"],  # color08
    ]

    if not os.path.isfile(wal_cache):
        return fallback

    try:
        with open(wal_cache, "r") as f:
            data = json.load(f)

        colors = data.get("colors", {})
        special = data.get("special", {})

        bg = special.get("background", "#282c34")
        fg = special.get("foreground", "#bbc2cf")

        return [
            [bg, bg],                                          # [0] bg
            [fg, fg],                                          # [1] fg
            [colors.get("color0", "#1c1f24"), colors.get("color0", "#1c1f24")],  # [2] dark
            [colors.get("color1", "#ff6c6b"), colors.get("color1", "#ff6c6b")],  # [3] red
            [colors.get("color2", "#98be65"), colors.get("color2", "#98be65")],  # [4] green
            [colors.get("color3", "#da8548"), colors.get("color3", "#da8548")],  # [5] yellow/orange
            [colors.get("color4", "#51afef"), colors.get("color4", "#51afef")],  # [6] blue
            [colors.get("color5", "#c678dd"), colors.get("color5", "#c678dd")],  # [7] magenta
            [colors.get("color6", "#46d9ff"), colors.get("color6", "#46d9ff")],  # [8] cyan (accent)
            [colors.get("color7", "#7d7d7d"), colors.get("color7", "#7d7d7d")],  # [9] light gray
        ]
    except (json.JSONDecodeError, KeyError, IOError):
        return fallback


# Глобальная переменная — используется в config.py как colors[0], colors[1] и т.д.
WalColors = load_wal_colors()

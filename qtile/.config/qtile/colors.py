import json
import os

CYBER_SOLAR_BASE = [
    ["#0d1a1e", "#0d1a1e"],
    ["#e8dcc0", "#e8dcc0"],
    ["#0a1418", "#0a1418"],
    ["#d97253", "#d97253"],
    ["#7fa063", "#7fa063"],
    ["#d4a24c", "#d4a24c"],
    ["#3a8e8e", "#3a8e8e"],
    ["#56b5b5", "#56b5b5"],
    ["#a86fa3", "#a86fa3"],
    ["#b8c4b8", "#b8c4b8"],
]

BAR_STATE_PATH = os.path.expanduser("~/.local/state/theme-hub/bar.json")
WALL_STATE_PATH = os.path.expanduser("~/.local/state/theme-hub/wall.json")
WAL_CACHE_PATH = os.path.expanduser("~/.cache/wal/colors.json")


def _ensure_dir(path):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def _read_json(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _write_json(path, data):
    _ensure_dir(path)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _palette_to_slots(palette):
    if isinstance(palette, list) and len(palette) >= 10:
        return [[c, c] for c in palette[:10]]
    return None


def load_bar_colors():
    data = _read_json(BAR_STATE_PATH)
    if data and "palette" in data:
        slots = _palette_to_slots(data["palette"])
        if slots:
            return slots
    return [list(c) for c in CYBER_SOLAR_BASE]


def load_wall_colors():
    data = _read_json(WALL_STATE_PATH)
    if data and "palette" in data:
        return data["palette"]
    data = _read_json(WAL_CACHE_PATH)
    if data:
        special = data.get("special", {})
        colors = data.get("colors", {})
        return {
            "background": special.get("background", CYBER_SOLAR_BASE[0][0]),
            "foreground": special.get("foreground", CYBER_SOLAR_BASE[1][0]),
            **{k: v for k, v in colors.items()},
        }
    return {}


def seed_bar_state():
    if os.path.isfile(BAR_STATE_PATH):
        return
    palette = [c[0] for c in CYBER_SOLAR_BASE]
    _write_json(BAR_STATE_PATH, {
        "source": "cyber-solar-base",
        "palette": palette,
    })


BarColors = load_bar_colors()
seed_bar_state()

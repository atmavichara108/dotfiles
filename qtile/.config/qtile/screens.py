from libqtile.config import Screen
from libqtile import bar
import widgets

def _is_wayland():
    try:
        from libqtile import qtile
        return qtile.core.name == "wayland"
    except Exception:
        return False

def init_screens():
    is_wayland = _is_wayland()
    return [
        Screen(top=bar.Bar(
            widgets=widgets.init_widgets_screen1(is_wayland),
            size=70,
            margin=[12, 16, 0, 16],
            background="#282c34e6",
            border_width=[0, 0, 0, 0],
            opacity=0.8,
        )),
        Screen(top=bar.Bar(
            widgets=widgets.init_widgets_screen2(is_wayland),
            size=80,
            margin=[12, 16, 0, 16],
            background=widgets.colors_list[0],
            opacity=0.9,
        )),
    ]

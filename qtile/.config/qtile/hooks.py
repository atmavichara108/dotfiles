import os
import subprocess
from libqtile import hook
from libqtile.config import Match
from libqtile import layout
from libqtile import qtile

def get_screen_core():
    try:
        return qtile.core.name
    except Exception:
        return "x11"

floating_layout = layout.Floating(
    border_width=2,
    float_rules=[
        *layout.Floating.default_float_rules,
        Match(wm_class="weathr-float"),
        Match(wm_class="gcal-float"),
        Match(wm_class="confirmreset"),
        Match(wm_class="dialog"),
        Match(wm_class="download"),
        Match(wm_class="error"),
        Match(wm_class="file_progress"),
        Match(wm_class="kdenlive"),
        Match(wm_class="makebranch"),
        Match(wm_class="maketag"),
        Match(wm_class="notification"),
        Match(wm_class="pinentry-gtk-2"),
        Match(wm_class="ssh-askpass"),
        Match(wm_class="toolbar"),
        Match(wm_class="Yad"),
        Match(title="branchdialog"),
        Match(title="Confirmation"),
        Match(title="emacs-run-launcher"),
        Match(title="pinentry"),
        Match(title="Qalculate!"),
        Match(title="tastycharts"),
        Match(title="tastytrade"),
        Match(title="tastytrade - Portfolio Report"),
        Match(wm_class="tasty.javafx.launcher.LauncherFxApp"),
    ]
)

@hook.subscribe.startup_once
def start_once():
    home = os.path.expanduser("~")
    core = get_screen_core()
    is_wayland = core == "wayland"
    if is_wayland:
        subprocess.call([home + "/.config/qtile/autostart-wayland"])
    else:
        subprocess.call([home + "/.config/qtile/autostart-x11"])

dgroups_key_binder = None
dgroups_app_rules = []
follow_mouse_focus = True
bring_front_click = False
cursor_warp = False
auto_fullscreen = True
focus_on_window_activation = "smart"
reconfigure_screens = True
auto_minimize = True
wl_input_rules = None
wmname = "LG3D"

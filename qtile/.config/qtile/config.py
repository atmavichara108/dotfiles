from libqtile import layout
from libqtile.config import Click, Drag, Group, Key, Match
from libqtile.lazy import lazy

import colors
import keys
import groups
import layouts
import widgets
import screens
import hooks

# Re-export from modules
keys = keys.keys
groups = groups.groups

# Extend keys with group-switching bindings
mod = "mod4"
for i in groups:
    keys.extend([
        Key([mod], i.name, lazy.group[i.name].toscreen(),
            desc="Switch to group {}".format(i.name)),
        Key([mod, "shift"], i.name, lazy.window.togroup(i.name, switch_group=False),
            desc="Move focused window to group {}".format(i.name)),
    ])

layouts = [
    layouts.monadtall_config,
    layouts.bsp_config,
]
widget_defaults = widgets.widget_defaults
extension_defaults = widgets.extension_defaults
screens = screens.init_screens()
floating_layout = hooks.floating_layout
dgroups_key_binder = hooks.dgroups_key_binder
dgroups_app_rules = hooks.dgroups_app_rules
follow_mouse_focus = hooks.follow_mouse_focus
bring_front_click = hooks.bring_front_click
cursor_warp = hooks.cursor_warp
auto_fullscreen = hooks.auto_fullscreen
focus_on_window_activation = hooks.focus_on_window_activation
reconfigure_screens = hooks.reconfigure_screens
auto_minimize = hooks.auto_minimize
wl_input_rules = hooks.wl_input_rules
wmname = hooks.wmname

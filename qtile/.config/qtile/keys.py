import os
from libqtile import qtile, extension
from libqtile.config import Click, Drag, Key, KeyChord
from libqtile.lazy import lazy
from layouts import (
    monadtall_config, bsp_config, columns_config, ratiotile_config,
    treetab_config, monadthreecol_config, slice_config,
    spiral_config, plasma_config, zoomy_config, floating_config,
)

mod = "mod4"
myTerm = "alacritty"
_default_proxy = "socks5://127.0.0.1:9050"
_proxy = os.environ.get("ALL_PROXY") or _default_proxy

myBrowser = "google-chrome-stable"

@lazy.layout.function
def add_treetab_section(layout):
    prompt = qtile.widgets_map["prompt"]
    prompt.start_input("Section name: ", layout.cmd_add_section)

@lazy.function
def minimize_all(qtile):
    for win in qtile.current_group.windows:
        if hasattr(win, "toggle_minimize"):
            win.toggle_minimize()

@lazy.function
def maximize_by_switching_layout(qtile):
    current_layout_name = qtile.current_group.layout.name
    if current_layout_name == 'monadtall':
        qtile.current_group.layout = 'max'
    elif current_layout_name == 'max':
        qtile.current_group.layout = 'monadtall'

keys = [
    Key([mod], "Return", lazy.spawn(myTerm), desc="Terminal"),
    Key([mod, "shift"], "Return", lazy.spawn("rofi -show drun -show-icons"), desc='Run Launcher'),
    Key([mod], "b", lazy.hide_show_bar(position='all'), desc="Toggles the bar to show/hide"),
    Key([mod], "Tab", lazy.next_layout(), desc="Toggle between layouts"),
    Key([mod], "w", lazy.window.kill(), desc="Kill focused window"),
    Key([mod, "shift"], "r", lazy.reload_config(), desc="Reload the config"),
    Key([mod, "control"], "r", lazy.restart(), desc="Restart Qtile (full)"),
    Key([mod, "shift"], "q", lazy.spawn("dm-logout -r"), desc="Logout menu"),
    Key([mod], "r", lazy.spawncmd(), desc="Spawn a command using a prompt widget"),
    Key([mod, "shift"], "T", lazy.spawn("conky-toggle"), desc="Conky toggle on/off"),
    Key([mod, "shift"], "z", lazy.spawn("translate_selected"), desc="Translate selected text"),

    Key([mod], "h", lazy.layout.left(), desc="Move focus to left"),
    Key([mod], "l", lazy.layout.right(), desc="Move focus to right"),
    Key([mod], "j", lazy.layout.down(), desc="Move focus down"),
    Key([mod], "k", lazy.layout.up(), desc="Move focus up"),
    Key([mod], "space", lazy.layout.next(), desc="Move window focus to other window"),

    Key([mod, "shift"], "w", lazy.spawn(myBrowser), desc='Web browser'),
    Key([mod, "shift"], "n", lazy.spawn(f"notion-app --proxy-server={_proxy}"), desc="Launch Notion"),
    Key([mod, "shift"], "g", lazy.spawn("gtk-launch genspark-tor"), desc="Genspark"),

    Key([mod, "shift"], "h",
        lazy.layout.shuffle_left(),
        lazy.layout.move_right().when(layout=["treetab"]),
        desc="Move window to the left/move tab left in treetab"),
    Key([mod, "shift"], "l",
        lazy.layout.shuffle_right(),
        lazy.layout.move_right().when(layout=["treetab"]),
        desc="Move window to the right/move tab right in treetab"),
    Key([mod, "shift"], "j",
        lazy.layout.shuffle_down(),
        lazy.layout.section_down().when(layout=["treetab"]),
        desc="Move window down/move down a section in treetab"),
    Key([mod, "shift"], "k",
        lazy.layout.shuffle_up(),
        lazy.layout.section_up().when(layout=["treetab"]),
        desc="Move window up/move up a section in treetab"),

    Key([mod, "shift"], "space", lazy.layout.toggle_split(), desc="Toggle between split and unsplit sides of stack"),
    Key([mod, "shift"], "a", add_treetab_section, desc='Prompt to add new section in treetab'),

    Key([mod], "equal",
        lazy.layout.grow_left().when(layout=["bsp", "columns"]),
        lazy.layout.grow().when(layout=["monadtall", "monadwide"]),
        desc="Grow window to the left"),
    Key([mod], "minus",
        lazy.layout.grow_right().when(layout=["bsp", "columns"]),
        lazy.layout.shrink().when(layout=["monadtall", "monadwide"]),
        desc="Shrink window to the right"),

    Key([mod, "control"], "h", lazy.layout.grow_left(), desc="Grow window to the left"),
    Key([mod, "control"], "l", lazy.layout.grow_right(), desc="Grow window to the right"),
    Key([mod, "control"], "j", lazy.layout.grow_down(), desc="Grow window down"),
    Key([mod, "control"], "k", lazy.layout.grow_up(), desc="Grow window up"),
    Key([mod], "n", lazy.layout.normalize(), desc="Reset all window sizes"),
    Key([mod], "m", lazy.layout.maximize(), desc='Toggle between min and max sizes'),
    Key([mod], "t", lazy.window.toggle_floating(), desc='toggle floating'),
    Key([mod], "f", maximize_by_switching_layout(), lazy.window.toggle_fullscreen(), desc='toggle fullscreen'),
    Key([mod, "shift"], "m", minimize_all(), desc="Toggle hide/show all windows on current group"),

    Key([mod], "period", lazy.next_screen(), desc='Move focus to next monitor'),
    Key([mod], "comma", lazy.prev_screen(), desc='Move focus to prev monitor'),

    Key([], "XF86AudioRaiseVolume", lazy.spawn("pactl set-sink-volume @DEFAULT_SINK@ +5%")),
    Key([], "XF86AudioLowerVolume", lazy.spawn("pactl set-sink-volume @DEFAULT_SINK@ -5%")),
    Key([], "XF86AudioMute", lazy.spawn("pactl set-sink-mute @DEFAULT_SINK@ toggle")),
    Key([], "XF86AudioMicMute", lazy.spawn("pactl set-source-mute @DEFAULT_SOURCE@ toggle")),
    Key([], "XF86MonBrightnessUp", lazy.spawn("brightnessctl set +5%")),
    Key([], "XF86MonBrightnessDown", lazy.spawn("brightnessctl set 5%-")),
    Key([], "XF86Bluetooth", lazy.spawn("bluetoothctl power $(bluetoothctl show | grep Powered | awk '{print $2}' | grep -q yes && echo 'off' || echo 'on')")),
    Key([mod], "F10", lazy.spawn("/usr/local/bin/lock.sh"), desc="Lock screen"),
    Key([], "XF86Favorites", lazy.spawn("rofimoji --action type copy")),
    Key([], "Print", lazy.spawn("flameshot gui")),

    Key(["mod1"], "Tab", lazy.screen.toggle_group(), desc="Toggle last workspaces"),
    Key(["mod1"], "Right", lazy.screen.next_group(), desc="Next workspace"),
    Key([mod], "Left", lazy.screen.prev_group(), desc="Previous workspace"),

    Key([mod], "F5", lazy.spawn("wal-set"), desc="Random wallpaper + new palette"),

    Key([mod, "shift"], "period", lazy.window.toscreen(1), desc="Move window to next monitor"),
    Key([mod, "shift"], "comma", lazy.window.toscreen(0), desc="Move window to prev monitor"),
    Key([mod], "F6", lazy.spawn(os.path.expanduser("~/.local/bin/monitor-setup")), desc="Detect monitors"),

    KeyChord([mod], "p", [
        Key([], "h", lazy.spawn("dm-hub -r"), desc='List all dmscripts'),
        Key([], "a", lazy.spawn("dm-sounds -r"), desc='Choose ambient sound'),
        Key([], "b", lazy.spawn("dm-setbg -r"), desc='Set background'),
        Key([], "c", lazy.spawn("dtos-colorscheme -r"), desc='Choose color scheme'),
        Key([], "e", lazy.spawn("dm-confedit -r"), desc='Choose a config file to edit'),
        Key([], "i", lazy.spawn("dm-maim -r"), desc='Take a screenshot'),
        Key([], "k", lazy.spawn("dm-kill -r"), desc='Kill processes'),
        Key([], "m", lazy.spawn("dm-man -r"), desc='View manpages'),
        Key([], "n", lazy.spawn("dm-note -r"), desc='Store and copy notes'),
        Key([], "o", lazy.spawn("dm-bookman -r"), desc='Browser bookmarks'),
        Key([], "p", lazy.spawn("rofi-pass"), desc='Password menu'),
        Key([], "q", lazy.spawn("dm-logout -r"), desc='Logout menu'),
        Key([], "r", lazy.spawn("dm-radio -r"), desc='Listen to online radio'),
        Key([], "s", lazy.spawn("dm-websearch -r"), desc='Search various engines'),
        Key([], "t", lazy.spawn("dm-translate -r"), desc='Translate text'),
        Key([], "u", lazy.spawn("dm-music -r"), desc='Toggle music mpc/mpd')
    ]),
]

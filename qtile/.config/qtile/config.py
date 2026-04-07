
import os
import subprocess
from libqtile import bar, extension, hook, layout, qtile, widget
from libqtile.config import Click, Drag, Group, Key, KeyChord, Match, Screen
from libqtile.lazy import lazy
from qtile_extras import widget as extrawidget
from qtile_extras.widget.decorations import RectDecoration, PowerLineDecoration, BorderDecoration
import colors
from pathlib import Path

HOME = Path.home()
WALLPAPERS_DIR = HOME / "wallpapers"
CONFIG_DIR = HOME / ".config" / "qtile"
ICONS_LAY = CONFIG_DIR / "icons" / "layouts"

IS_WAYLAND = qtile.core.name == "wayland"
IS_X11 = qtile.core.name == "x11"

mod = "mod4"              # Sets mod key to SUPER/WINDOWS
myTerm = "alacritty"      # My terminal of choice
myBrowserTor = "google-chrome-stable --proxy-server=socks5://127.0.0.1:9050"
myBrowser = "google-chrome-stable"
myEmacs = "emacsclient -c -a 'emacs' "

# Allows you to input a name when adding treetab section.
@lazy.layout.function
def add_treetab_section(layout):
    prompt = qtile.widgets_map["prompt"]
    prompt.start_input("Section name: ", layout.cmd_add_section)

# A function for hide/show all the windows in a group
@lazy.function
def minimize_all(qtile):
    for win in qtile.current_group.windows:
        if hasattr(win, "toggle_minimize"):
            win.toggle_minimize()
           
# A function for toggling between MAX and MONADTALL layouts
@lazy.function
def maximize_by_switching_layout(qtile):
    current_layout_name = qtile.current_group.layout.name
    if current_layout_name == 'monadtall':
        qtile.current_group.layout = 'max'
    elif current_layout_name == 'max':
        qtile.current_group.layout = 'monadtall'

keys = [
    # The essentials
    Key([mod], "Return", lazy.spawn(myTerm), desc="Terminal"),
    # Use 'rofi' as your run launcher.
    Key([mod, "shift"], "Return", lazy.spawn("rofi -show drun -show-icons"), desc='Run Launcher'),
    Key([mod], "b", lazy.hide_show_bar(position='all'), desc="Toggles the bar to show/hide"),
    Key([mod], "Tab", lazy.next_layout(), desc="Toggle between layouts"),
    Key([mod], "w", lazy.window.kill(), desc="Kill focused window"),
    Key([mod, "shift"], "r", lazy.reload_config(), desc="Reload the config"),
    Key([mod, "control"], "r", lazy.restart(), desc="Restart Qtile (full)"),
    Key([mod, "shift"], "q", lazy.spawn("dm-logout -r"), desc="Logout menu"),
    Key([mod], "r", lazy.spawncmd(), desc="Spawn a command using a prompt widget"),
    Key([mod, "shift"], "T", lazy.spawn("conky-toggle"), desc="Conky toggle on/off"),
    # Перевод выделенного текста (Rofi)
    Key([mod, "shift"], "z", lazy.spawn("translate_selected"), desc="Translate selected text"),
    # Switch between windows
    # Some layouts like 'monadtall' only need to use j/k to move
    # through the stack, but other layouts like 'columns' will
    # require all four directions h/j/k/l to move around.
    Key([mod], "h", lazy.layout.left(), desc="Move focus to left"),
    Key([mod], "l", lazy.layout.right(), desc="Move focus to right"),
    Key([mod], "j", lazy.layout.down(), desc="Move focus down"),
    Key([mod], "k", lazy.layout.up(), desc="Move focus up"),
    Key([mod], "space", lazy.layout.next(), desc="Move window focus to other window"),

    #Apps
    Key([mod, "shift"], "w", lazy.spawn(myBrowser),
        desc='Web browser'),
    Key([mod, "shift"], "n", lazy.spawn("notion-app --proxy-server=socks5://127.0.0.1:9050"),
        desc="Launch Notion"),
    Key([mod, "shift"], "g", lazy.spawn("gtk-launch genspark-tor"),
        desc="Genspark"),

    # Move windows between left/right columns or move up/down in current stack.
    # Moving out of range in Columns layout will create new column.
    Key([mod, "shift"], "h",
        lazy.layout.shuffle_left(),
        lazy.layout.move_left().when(layout=["treetab"]),
        desc="Move window to the left/move tab left in treetab"),

    Key([mod, "shift"], "l",
        lazy.layout.shuffle_right(),
        lazy.layout.move_right().when(layout=["treetab"]),
        desc="Move window to the right/move tab right in treetab"),

    Key([mod, "shift"], "j",
        lazy.layout.shuffle_down(),
        lazy.layout.section_down().when(layout=["treetab"]),
        desc="Move window down/move down a section in treetab"
    ),
    Key([mod, "shift"], "k",
        lazy.layout.shuffle_up(),
        lazy.layout.section_up().when(layout=["treetab"]),
        desc="Move window downup/move up a section in treetab"
    ),

    # Toggle between split and unsplit sides of stack.
    # Split = all windows displayed
    # Unsplit = 1 window displayed, like Max layout, but still with
    # multiple stack panes
    Key([mod, "shift"], "space", lazy.layout.toggle_split(), desc="Toggle between split and unsplit sides of stack"),

    # Treetab prompt
    Key([mod, "shift"], "a", add_treetab_section, desc='Prompt to add new section in treetab'),

    # Grow/shrink windows left/right. 
    # This is mainly for the 'monadtall' and 'monadwide' layouts
    # although it does also work in the 'bsp' and 'columns' layouts.
    Key([mod], "equal",
        lazy.layout.grow_left().when(layout=["bsp", "columns"]),
        lazy.layout.grow().when(layout=["monadtall", "monadwide"]),
        desc="Grow window to the left"
    ),
    Key([mod], "minus",
        lazy.layout.grow_right().when(layout=["bsp", "columns"]),
        lazy.layout.shrink().when(layout=["monadtall", "monadwide"]),
        desc="Grow window to the left"
    ),

    # Grow windows up, down, left, right.  Only works in certain layouts.
    # Works in 'bsp' and 'columns' layout.
    Key([mod, "control"], "h", lazy.layout.grow_left(), desc="Grow window to the left"),
    Key([mod, "control"], "l", lazy.layout.grow_right(), desc="Grow window to the right"),
    Key([mod, "control"], "j", lazy.layout.grow_down(), desc="Grow window down"),
    Key([mod, "control"], "k", lazy.layout.grow_up(), desc="Grow window up"),
    Key([mod], "n", lazy.layout.normalize(), desc="Reset all window sizes"),
    Key([mod], "m", lazy.layout.maximize(), desc='Toggle between min and max sizes'),
    Key([mod], "t", lazy.window.toggle_floating(), desc='toggle floating'),
    Key([mod], "f", maximize_by_switching_layout(), lazy.window.toggle_fullscreen(), desc='toggle fullscreen'),
    Key([mod, "shift"], "m", minimize_all(), desc="Toggle hide/show all windows on current group"),

    # Switch focus of monitors
    Key([mod], "period", lazy.next_screen(), desc='Move focus to next monitor'),
    Key([mod], "comma", lazy.prev_screen(), desc='Move focus to prev monitor'),

    # Громкость (pactl — твой основной инструмент)
    Key([], "XF86AudioRaiseVolume", lazy.spawn("pactl set-sink-volume @DEFAULT_SINK@ +5%")),
    Key([], "XF86AudioLowerVolume", lazy.spawn("pactl set-sink-volume @DEFAULT_SINK@ -5%")),
    Key([], "XF86AudioMute", lazy.spawn("pactl set-sink-mute @DEFAULT_SINK@ toggle")),

    # Микрофон
    Key([], "XF86AudioMicMute", lazy.spawn("pactl set-source-mute @DEFAULT_SOURCE@ toggle")),

    # Яркость
    Key([], "XF86MonBrightnessUp", lazy.spawn("brightnessctl set +5%")),
    Key([], "XF86MonBrightnessDown", lazy.spawn("brightnessctl set 5%-")),

    # Переключение дисплеев (если есть внешний монитор)
    # Key([], "XF86Display", lazy.spawn("autorandr --change || xrandr --auto")),

    # WiFi (F8) — вкл/выкл через nmcli или rfkill
    # Key([], "XF86WLAN", lazy.spawn("nmcli radio wifi toggle")),

    # ThinkVantage/Tools (F9) — обычно система/диагностика, можно назначить на меню или терминал
    # Key([], "XF86Tools", lazy.spawn("alacritty -e htop")),

    # Bluetooth (F10) + locksrine
    Key([], "XF86Bluetooth", lazy.spawn("bluetoothctl power $(bluetoothctl show | grep Powered | awk '{print $2}' | grep -q yes && echo 'off' || echo 'on')")),
    Key([mod], "F10", lazy.spawn("/usr/local/bin/lock.sh"),
        desc="Lock screen"),

    # Favorites (F12) — твоя кастомизация, например rofi drun
    Key([], "XF86Favorites", lazy.spawn("rofimoji --action type copy")),
    
    # Открыть flameshot для выделения области
    Key([], "Print", lazy.spawn("flameshot gui")),

    # Быстрое переключение между двумя последними (Alt+Tab для воркспейсов)
    Key(["mod1"], "Tab", lazy.screen.toggle_group(), desc="Toggle last workspaces"),

    # Цикл по воркспейсам (дополнительно)
    Key(["mod1"], "Right", lazy.screen.next_group(), desc="Next workspace"),
    Key([mod], "Left",  lazy.screen.prev_group(), desc="Previous workspace"),
    
    # Смена обоев
    Key([mod], "F5", lazy.spawn("wal-set"), desc="Random wallpaper + new palette"),

    # Перемещение окон между мониторами
    Key([mod, "shift"], "period",
        lazy.window.toscreen(1),
        desc="Move window to next monitor"),
    Key([mod, "shift"], "comma",
        lazy.window.toscreen(0),
        desc="Move window to prev monitor"),

    # обновить конфигурацию мониторов при включении/отключении второго монитора
    Key([mod], "F6", lazy.spawn(os.path.expanduser("~/.local/bin/monitor-setup")), 
        desc="Detect monitors"),

    # Dmenu/rofi scripts launched using the key chord SUPER+p followed by 'key'
    KeyChord([mod], "p", [
        Key([], "h", lazy.spawn("dm-hub -r"), desc='List all dmscripts'),
        Key([], "a", lazy.spawn("dm-sounds -r"), desc='Choose ambient sound'),
        Key([], "b", lazy.spawn("dm-setbg -r"), desc='Set background'),
        Key([], "c", lazy.spawn("dtos-colorscheme -r"), desc='Choose color scheme'),
        Key([], "e", lazy.spawn("dm-confedit -r"), desc='Choose a config file to edit'),
        Key([], "i", lazy.spawn("dm-maim -r"), desc='Take a screenshot'),
        Key([], "k", lazy.spawn("dm-kill -r"), desc='Kill processes '),
        Key([], "m", lazy.spawn("dm-man -r"), desc='View manpages'),
        Key([], "n", lazy.spawn("dm-note -r"), desc='Store and copy notes'),
        Key([], "o", lazy.spawn("dm-bookman -r"), desc='Browser bookmarks'),
        Key([], "p", lazy.spawn("rofi-pass"), desc='Password menu'),
        Key([], "q", lazy.spawn("dm-logout -r"), desc='Logout menu'),
        Key([], "r", lazy.spawn("dm-radio -r"), desc='Listen to online radio'),
        Key([], "s", lazy.spawn("dm-websearch -r"), desc='Search various engines'),
        Key([], "t", lazy.spawn("dm-translate -r"), desc='Translate text'),
        Key([], "u", lazy.spawn("dm-music -r"), desc='Toggle music mpc/mpd')
    ])
]


colors = colors.WalColors

layout_theme = {"border_width": 3,
                "margin": 8,
                "border_focus": colors[8],
                "border_normal": colors[0]
                }

# === Индивидуальные настройки для каждого layout ===

# MonadTall — DEV основной
monadtall_config = layout.MonadTall(
    **layout_theme,
    ratio=0.55,                    # мастер 55% ширины
    max_ratio=0.75,
    min_ratio=0.30,
    change_ratio=0.05,
    single_border_width=0,         # одно окно — без рамки
    single_margin=0,               # одно окно — без отступов
    new_client_position="after_current",
)

# Bsp — универсальный гибкий
bsp_config = layout.Bsp(
    **layout_theme,
    fair=False,                    # новое окно делит текущее, а не ищет самую короткую ветку
    grow_amount=10,                # шаг ресайза в пикселях (на 4K 10 — адекватно)
    ratio=1.6,                     # выше порога → горизонтальное деление, ниже → вертикальное
    border_on_single=False,
    margin_on_single=0,
)

# Columns
columns_config = layout.Columns(
    **layout_theme,
    num_columns=2,                 # старт с 2 колонок
    fair=False,                    # новые окна в текущую колонку, не в самую пустую
    insert_position=1,             # новые окна снизу текущего
    initial_ratio=1.2,             # первая колонка чуть шире второй
    border_on_single=False,
    border_focus_stack=colors[7],  # фиолетовый для stacked-колонок (отличать от split)
    border_normal_stack=colors[0],
    wrap_focus_columns=True,
    wrap_focus_rows=True,
    split=True,                    # по умолчанию split (все окна видны)
)

# RatioTile — равномерная сетка
ratiotile_config = layout.RatioTile(
    **layout_theme,
    ratio=1.618,                   # золотое сечение — окна стремятся к этому соотношению
    ratio_increment=0.1,
    fancy=True,                    # альтернативный алгоритм расчёта размеров (экспериментируй)
)

# TreeTab — навигация по дереву
treetab_config = layout.TreeTab(
    font="Ubuntu Bold",
    fontsize=28,                   # для 4K
    border_width=0,
    bg_color="#282c34e6",
    active_bg=colors[8],
    active_fg=colors[2],
    inactive_bg=colors[1],
    inactive_fg=colors[0],
    padding_left=16,
    padding_x=16,
    padding_y=12,
    sections=["MAIN", "SECONDARY", "OTHER"],
    section_fontsize=31,           # для 4K
    section_fg=colors[7],
    section_top=15,
    section_bottom=15,
    level_shift=8,
    vspace=3,
    panel_width=200,               # шире для 4K чтобы имена окон были читаемы
)

# MonadThreeCol — три колонки с центральным мастером
monadthreecol_config = layout.MonadThreeCol(
    **layout_theme,
    ratio=0.45,                    # мастер 45% (центр), по бокам по ~27.5%
    main_centered=True,            # мастер в центре
    max_ratio=0.65,
    min_ratio=0.30,
    change_ratio=0.05,
    new_client_position="top",
    single_border_width=0,
    single_margin=0,
)

# Slice — боковая панель + fallback layout
# Пример: cmus (музыкальный плеер) слева, остальное — RatioTile
slice_config = layout.Slice(
    side="left",
    width=600,                     # 600px на 4K ≈ 15% экрана
    match=Match(wm_class="cmus"),  # окно, которое встанет в slice
    fallback=layout.RatioTile(     # что делать с остальными окнами
        **layout_theme,
        ratio=1.618,
    ),
)

# Spiral — золотое сечение
spiral_config = layout.Spiral(
    **layout_theme,
    main_pane="left",              # главное окно слева
    clockwise=True,                # спираль по часовой
    ratio=0.618,                   # золотое сечение
    ratio_increment=0.05,
    main_pane_ratio=0.55,          # мастер 55%
    new_client_position="top",
    border_on_single=False,
)

# Plasma — управляемое дерево
plasma_config = layout.Plasma(
    **layout_theme,
    border_focus_fixed=colors[7],  # фиолетовый для окон с фиксированным размером
    border_normal_fixed=colors[0],
    border_width_single=0,
    fair=False,                    # не отбирать место у фиксированных окон
)

# Zoomy — фокус + превью
zoomy_config = layout.Zoomy(
    **layout_theme,
)

# Floating — свободное размещение
floating_config = layout.Floating(
    **layout_theme,
)


# === Группы с индивидуальными layouts ===

group_configs = [
    # 1 - ॐ (ОМ / АУМ) — Изначальный Звук
    {"name": "1", "label": "ॐ", "layouts": [
        monadtall_config,
    ]},
    # 2 - श्री"  (Шри) — Сияние Благодати
    {"name": "2", "label": "श्री", "layouts": [
        bsp_config,
        columns_config,
    ]},
    # 3 - ह्रीं — (Хрим) — Семя Шакти
    {"name": "3", "label": "ह्रीं", "layouts": [
        treetab_config,
        ratiotile_config,
    ]},
    # 4 - क्लीं — притяжение
    {"name": "4", "label": "क्लीं", "layouts": [
        monadthreecol_config,
        zoomy_config,
    ]},
    # 5 - ऐं — знание/Сарасвати
    {"name": "5", "label": "ऐं", "layouts": [
        bsp_config,
        treetab_config,
    ]},
    # 6 - सौः — лунная энергия
    {"name": "6", "label": "सौः", "layouts": [
        columns_config,
        plasma_config,
    ]},
    # 7 - हूं — защита/Шива
    {"name": "7", "label": "हूं", "layouts": [
        plasma_config,
    ]},
    # 8 - रां — огонь (Манипура)
    {"name": "8", "label": "रां", "layouts": [
        spiral_config,
        ratiotile_config,
    ]},
    # 9 - वं — вода (Свадхистана)
    {"name": "9", "label": "वं", "layouts": [
        slice_config,
    ]},
    # 0 - लं — земля (Муладхара)
    {"name": "0", "label": "लं", "layouts": [
        floating_config,
    ]},
]

groups = []
for conf in group_configs:
    groups.append(
        Group(
            name=conf["name"],
            label=conf["label"],
            layouts=conf["layouts"],
            layout=conf["layouts"][0].name,
        )
    )

for i in groups:
    keys.extend([
        Key([mod], i.name, lazy.group[i.name].toscreen(),
            desc="Switch to group {}".format(i.name)),
        Key([mod, "shift"], i.name, lazy.window.togroup(i.name, switch_group=False),
            desc="Move focused window to group {}".format(i.name)),
    ])
layouts = [
    layout.MonadTall(**layout_theme),
    layout.Bsp(**layout_theme),
]

# ============================================================
# ВИДЖЕТЫ — НАСТРОЙКИ ПО УМОЛЧАНИЮ
# ============================================================

widget_defaults = dict(
    font="Ubuntu Bold",
    fontsize = 28,
    padding = 0,
    background=colors[0]
)

extension_defaults = widget_defaults.copy()

# ============================================================
# ДЕКОРАТОРЫ — ПЕРЕИСПОЛЬЗУЕМЫЕ СТИЛИ
# ============================================================

# PowerLine стрелки между секциями
powerline_right = {"decorations": [PowerLineDecoration(path="arrow_right", size=16)]}
powerline_left = {"decorations": [PowerLineDecoration(path="arrow_left", size=16)]}

# Скруглённый фон для групп виджетов
def rect_decoration(color, radius=8):
    return {"decorations": [RectDecoration(colour=color, radius=radius, filled=True, padding_y=5, group=True)]}

# Нижний акцент
def border_accent(color):
    return {"decorations": [BorderDecoration(colour=color, border_width=[0, 0, 3, 0])]}


# ============================================================
# ФУНКЦИИ-ХЕЛПЕРЫ
# ============================================================

# Раскладка клавиатуры без конфликта с alt+shift
def get_keyboard_layout():
    try:
        output = subprocess.check_output(
            ["xkblayout-state", "print", "%s"], text=True
        ).strip().upper()
        return output
    except FileNotFoundError:
        # fallback если xkblayout-state не установлен
        try:
            output = subprocess.check_output(
                ["setxkbmap", "-query"], text=True
            )
            for line in output.splitlines():
                if "layout" in line:
                    layouts = line.split(":")[1].strip().split(",")
                    # Определяем активную через xset
                    xset = subprocess.check_output(
                        "xset -q | grep -oP 'LED mask:\\s+\\K\\d+'",
                        shell=True, text=True
                    ).strip()
                    # Bit 12 = group2 active
                    idx = 1 if int(xset, 16) & (1 << 12) else 0
                    return layouts[min(idx, len(layouts)-1)].upper()
        except Exception:
            return "??"
    return "??"


# ============================================================
# SYSTRAY (X11/WAYLAND)
# ============================================================

def tray_widget():
    if IS_WAYLAND:
        return widget.StatusNotifier(padding=6)
    else:
        return widget.Systray(padding=6)

# ============================================================
# СБОРКА ВИДЖЕТОВ
# ============================================================

def init_widgets_list(include_tray=True):
    widgets_list = [

        # ── ЛЕВАЯ СЕКЦИЯ: Лого + Groups + Layout ──────────────

        widget.Spacer(length=12),

        # Логотип (замени на свою иконку)
        widget.Image(
            filename="~/.config/qtile/icons/logo.svg",
            scale=True,
            margin=6,
            mouse_callbacks={"Button1": lambda: qtile.cmd_spawn("rofi -show drun -show-icons")},
            **rect_decoration(colors[2]),
        ),

        widget.Spacer(length=8),

        # Индикатор активного KeyChord
        extrawidget.Chord(
            fontsize=25,
            foreground=colors[3],
            fmt="🎹 {}",
            padding=8,
        ),

        # Воркспейсы (санскрит биджа)
        extrawidget.GroupBox(
            fontsize=39,
            margin_y=5,
            margin_x=16,
            padding_y=0,
            padding_x=6,
            borderwidth=4,
            active=colors[3],
            inactive=colors[9],
            rounded=False,
            highlight_color=colors[0],
            highlight_method="line",
            this_current_screen_border=colors[5],
            this_screen_border=colors[8],
            other_current_screen_border=colors[5],
            other_screen_border=colors[8],
            urgent_alert_method="line",
            urgent_border=colors[6],
            disable_drag=True,
            **border_accent(colors[0]),
        ),

        widget.Spacer(length=8),

        # Текущий layout (иконка)
        extrawidget.CurrentLayoutIcon(
            custom_icon_paths=[os.path.expanduser("~/.config/qtile/icons/layout/"),],
            scale=1.1,
            padding=0,
            **rect_decoration(colors[2]),
        ),

        widget.Spacer(length=8),

        # Количество окон в группе
        extrawidget.WindowCount(
            fmt="[{}]",
            fontsize=25,
            foreground=colors[9],
            padding=4,
        ),

        # Имя текущего окна
        extrawidget.WindowName(
            foreground=colors[6],
            max_chars=45,
            padding=12,
            fontsize=25,
        ),

        # ── ЦЕНТР: Растяжка + Часы + Растяжка ────────────────

        widget.Spacer(length=bar.STRETCH),

        extrawidget.Clock(
            format="  %a %d %b   %H:%M  ",
            fontsize=33,
            foreground=colors[2],
            padding=0,
            mouse_callbacks={
                "Button1": lambda: qtile.cmd_spawn(
                    myTerm + " --class gcal-float -e calcurse"
                ),
            },
            **rect_decoration(colors[6], radius=12),
        ),

        widget.Spacer(length=bar.STRETCH),

        # ── ПРАВАЯ СЕКЦИЯ: WidgetBox + Quick Info + Tray ──────

        # WidgetBox: Системный мониторинг (сворачиваемый)
        extrawidget.WidgetBox(
            text_closed=" ⏵ SYS ",
            text_open=" ⏷ SYS ",
            fontsize=28,
            foreground=colors[8],
            **rect_decoration(colors[2]),
            widgets=[
                extrawidget.CPU(
                    format=" CPU {load_percent:>4}% ",
                    fontsize=28,
                    foreground=colors[4],
                    update_interval=3,
                    mouse_callbacks={"Button1": lambda: qtile.cmd_spawn(myTerm + " -e htop")},
                ),
                extrawidget.Memory(
                    format=" MEM {MemUsed:.0f}{mm} ",
                    fontsize=28,
                    foreground=colors[8],
                    measure_mem="M",
                    update_interval=3,
                    mouse_callbacks={"Button1": lambda: qtile.cmd_spawn(myTerm + " -e htop")},
                ),
                extrawidget.ThermalSensor(
                    tag_sensor="Core 0",
                    fontsize=28,
                    foreground=colors[5],
                    foreground_alert=colors[3],
                    threshold=75,
                    fmt=" TEMP {} ",
                    update_interval=5,
                ),
                extrawidget.NvidiaSensors(
                    format=" GPU {temp}°C ",
                    fontsize=28,
                    foreground=colors[5],
                    foreground_alert=colors[3],
                    threshold=80,
                ),
                extrawidget.DF(
                    partition="/",
                    format=" DISK {uf}{m} ",
                    fontsize=28,
                    foreground=colors[5],
                    visible_on_warn=False,
                    update_interval=60,
                ),
            ],
        ),

        widget.Spacer(length=8),

        # WidgetBox: Мультимедиа (сворачиваемый)
        extrawidget.WidgetBox(
            text_closed=" ⏵ ♫ ",
            text_open=" ⏷ ♫ ",
            fontsize=28,
            foreground=colors[7],
            **rect_decoration(colors[2]),
            widgets=[
                extrawidget.Mpris2(
                    name="browser",
                    format="{xesam:title} - {xesam:artist}",
                    fmt=" {} ",
                    fontsize=28,
                    max_chars=35,
                    foreground=colors[7],
                    paused_text="⏸ {track}",
                    width=220,
                    scroll_fixed_width=True,
                    scroll=True,
                ),
            ],
        ),

        widget.Spacer(length=8),

        # Раскладка клавиатуры (без конфликта)
        extrawidget.GenPollText(
            func=get_keyboard_layout,
            update_interval=0.5,
            fontsize=28,
            foreground=colors[1],
            fmt=" {} ",
            padding=8,
            **rect_decoration(colors[2]),
        ),

        extrawidget.Net(
            format=" {down:.0f}{down_suffix}↓ {up:.0f}{up_suffix}↑ ",
            fontsize=28,
            foreground=colors[6],
            update_interval=3,
        ),

        widget.Spacer(length=8),

        # Громкость
        extrawidget.Volume(
            fmt=" ♪ {} ",
            fontsize=28,
            foreground=colors[7],
            step=5,
            padding=4,
            mouse_callbacks={"Button3": lambda: qtile.cmd_spawn("pavucontrol")},
        ),

        widget.Spacer(length=4),

        # Wi-Fi
        # extrawidget.Wlan(
        #     interface="wlp4s0",
        #     format=" {essid} {percent:2.0%} ",
        #     disconnected_message=" ⚠ WiFi ",
        #     fontsize=28,
        #     foreground=colors[6],
        #     padding=4,
        #     mouse_callbacks={"Button1": lambda: qtile.cmd_spawn(myTerm + " -e nmtui")},
        # ),
        #
        # widget.Spacer(length=4),

        # Батарея
        extrawidget.Battery(
            format=" {char}{percent:2.0%} ",
            fontsize=22,
            charge_char="⚡",
            discharge_char="🔋",
            full_char="✓ ",
            empty_char="✗ ",
            low_foreground=colors[3],
            low_percentage=0.15,
            notify_below=15,
            foreground=colors[4],
            update_interval=30,
            **border_accent(colors[4]),
        ),

        widget.Spacer(length=4),

        # Погода (одна строка)
        widget.GenPollText(
            func=lambda: subprocess.check_output(
                ["curl", "-s", "wttr.in/47.519679,40.115877?format=%c+%t&m"],
                timeout=10,
            ).decode("utf-8").strip(),
            update_interval=60,
            fontsize=28,
            foreground=colors[5],
            padding=4,
            mouse_callbacks={
                "Button1": lambda: qtile.cmd_spawn(
                    myTerm + " --class weathr-float,weathr-float -o 'window.dimensions.columns=90' -o 'window.dimensions.lines=30' -e weathr"
                ),
            },
        ),

        widget.Spacer(length=8),

        # Pomodoro
        widget.Pomodoro(
            fontsize=26,
            color_active=colors[3],
            color_break=colors[4],
            color_inactive=colors[9],
            length_pomodori=25,
            length_short_break=5,
            length_long_break=15,
            num_pomodori=4,
            fmt="  {} ",
            prefix_inactive="🍅",
            prefix_active="⏱",
            prefix_break="☕",
            prefix_long_break="🌿",
            prefix_paused="⏸",
            notification_on=True,
            update_interval=1,
        ),

        widget.Spacer(length=8),

        # Уведомления
        extrawidget.Notify(
            fontsize=25,
            foreground=colors[1],
            default_timeout=5,
            fmt=" {} ",
        ),

    ]

    # Systray добавляем только на основной монитор
    if include_tray:
        widgets_list.extend([
            widget.Spacer(length=8),
            tray_widget(),
            widget.Spacer(length=12),
        ])
    else:
        widgets_list.append(widget.Spacer(length=12))

    return widgets_list


# ============================================================
# ЭКРАНЫ
# ============================================================

def init_widgets_screen1():
    return init_widgets_list(include_tray=True)

def init_widgets_screen2():
    return init_widgets_list(include_tray=False)

def init_screens():
    return [
        Screen(top=bar.Bar(
            widgets=init_widgets_screen1(),
            size=70,
            margin=[12, 16, 0, 16],
            # background=colors[0],
            background="#282c34e6",  # раскомментируй для полупрозрачности
            border_width=[0, 0, 0, 0],
            opacity=0.8,
        )),
        Screen(top=bar.Bar(
            widgets=init_widgets_screen2(),
            size=80,
            margin=[12, 16, 0, 16],
            background=colors[0],
            opacity=0.9,
        )),
    ]

if __name__ in ["config", "__main__"]:
    screens = init_screens()


def window_to_prev_group(qtile):
    if qtile.currentWindow is not None:
        i = qtile.groups.index(qtile.currentGroup)
        qtile.currentWindow.togroup(qtile.groups[i - 1].name)

def window_to_next_group(qtile):
    if qtile.currentWindow is not None:
        i = qtile.groups.index(qtile.currentGroup)
        qtile.currentWindow.togroup(qtile.groups[i + 1].name)

def window_to_previous_screen(qtile):
    i = qtile.screens.index(qtile.current_screen)
    if i != 0:
        group = qtile.screens[i - 1].group.name
        qtile.current_window.togroup(group)

def window_to_next_screen(qtile):
    i = qtile.screens.index(qtile.current_screen)
    if i + 1 != len(qtile.screens):
        group = qtile.screens[i + 1].group.name
        qtile.current_window.togroup(group)

def switch_screens(qtile):
    i = qtile.screens.index(qtile.current_screen)
    group = qtile.screens[i - 1].group
    qtile.current_screen.set_group(group)

mouse = [
    Drag([mod], "Button1", lazy.window.set_position_floating(), start=lazy.window.get_position()),
    Drag([mod], "Button3", lazy.window.set_size_floating(), start=lazy.window.get_size()),
    Click([mod], "Button2", lazy.window.bring_to_front()),
    # Drag(["mod1"], "Button1", lazy.window.set_position_floating(), start=lazy.window.get_position()),
    # Drag(["mod1"], "Button3", lazy.window.set_size_floating(), start=lazy.window.get_size()),
    # Click(["mod1"], "Button2", lazy.window.bring_to_front()),
]

dgroups_key_binder = None
dgroups_app_rules = []  # type: list
follow_mouse_focus = True
bring_front_click = False
cursor_warp = False
floating_layout = layout.Floating(
    border_focus=colors[8],
    border_width=2,
    float_rules=[
        # Run the utility of `xprop` to see the wm class and name of an X client.
        *layout.Floating.default_float_rules,
        Match(wm_class="weathr-float"),     # weathr по клику на погоду
        Match(wm_class="gcal-float"),       # calendar по клику на часы
        Match(wm_class="confirmreset"),    # gitk
        Match(wm_class="dialog"),          # dialog boxes
        Match(wm_class="download"),        # downloads
        Match(wm_class="error"),           # error msgs
        Match(wm_class="file_progress"),   # file progress boxes
        Match(wm_class='kdenlive'),        # kdenlive
        Match(wm_class="makebranch"),      # gitk
        Match(wm_class="maketag"),         # gitk
        Match(wm_class="notification"),    # notifications
        Match(wm_class='pinentry-gtk-2'),  # GPG key password entry
        Match(wm_class="ssh-askpass"),     # ssh-askpass
        Match(wm_class="toolbar"),         # toolbars
        Match(wm_class="Yad"),             # yad boxes
        Match(title="branchdialog"),       # gitk
        Match(title='Confirmation'),       # tastyworks exit box
        Match(title="emacs-run-launcher"), # dt/emacs-run-launcher
        Match(title="pinentry"),           # GPG key password entry
        Match(title='Qalculate!'),         # qalculate-gtk
        Match(title="tastycharts"),        # tastytrade pop-out charts
        Match(title="tastytrade"),         # tastytrade pop-out side gutter
        Match(title="tastytrade - Portfolio Report"), # tastytrade pop-out allocation
        Match(wm_class="tasty.javafx.launcher.LauncherFxApp"), # tastytrade settings
    ]
)
auto_fullscreen = True
focus_on_window_activation = "smart"
reconfigure_screens = True

# If things like steam games want to auto-minimize themselves when losing
# focus, should we respect this or not?
auto_minimize = True

# When using the Wayland backend, this can be used to configure input devices.
wl_input_rules = None

@hook.subscribe.startup_once
def start_once():
    home = os.path.expanduser("~")
    if IS_WAYLAND:
        subprocess.call([home + "/.config/qtile/autostart-wayland"])
    else:
        subprocess.call([home + "/.config/qtile/autostart-x11"])

#X: Gasp! We're lying here. In fact, nobody really uses or cares about this
# string besides java UI toolkits; you can see several discussions on the
# mailing lists, GitHub issues, and other WM documentation that suggest setting
# this string if your java app doesn't work correctly. We may as well just lie
# and say that we're a working one by default.
#
# We choose LG3D to maximize irony: it is a 3D non-reparenting WM written in
# java that happens to be on java's whitelist.
wmname = "LG3D"

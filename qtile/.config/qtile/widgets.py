import subprocess
from libqtile import bar, qtile, widget
from libqtile.config import Screen
from qtile_extras import widget as extrawidget
from qtile_extras.widget.decorations import PowerLineDecoration, RectDecoration, BorderDecoration
import colors
from keys import myTerm

colors_list = colors.BarColors

widget_defaults = dict(
    font="Ubuntu Bold",
    fontsize=28,
    padding=0,
    background=colors_list[0],
)

extension_defaults = widget_defaults.copy()

def pill(color, radius=10):
    return {"decorations": [RectDecoration(colour=color, radius=radius, filled=True, padding_y=4, group=True)]}

def get_keyboard_layout():
    try:
        output = subprocess.check_output(
            ["xkblayout-state", "print", "%s"], text=True
        ).strip().upper()
        return output
    except FileNotFoundError:
        try:
            output = subprocess.check_output(
                ["setxkbmap", "-query"], text=True
            )
            for line in output.splitlines():
                if "layout" in line:
                    layouts = line.split(":")[1].strip().split(",")
                    xset = subprocess.check_output(
                        "xset -q | grep -oP 'LED mask:\\s+\\K\\d+'",
                        shell=True, text=True
                    ).strip()
                    idx = 1 if int(xset, 16) & (1 << 12) else 0
                    return layouts[min(idx, len(layouts)-1)].upper()
        except Exception:
            return "??"
    return "??"

def get_weather():
    try:
        output = subprocess.check_output(
            ["curl", "-s", "wttr.in/47.519679,40.115877?format=%c+%t&m"],
            timeout=10,
        ).decode("utf-8").strip()
        if "<" in output or len(output) > 30:
            return "  --"
        return output
    except Exception:
        return "  --"

def tray_widget(is_wayland):
    if is_wayland:
        return widget.StatusNotifier(icon_size=28, padding=10)
    else:
        return widget.Systray(icon_size=28, padding=10)

def init_widgets_list(include_tray=True, is_wayland=False):
    widgets_list = [
        widget.Spacer(length=12),
        widget.Image(
            filename="~/.config/qtile/icons/logo.png",
            scale=True,
            margin=6,
            mouse_callbacks={"Button1": lambda: qtile.cmd_spawn("rofi -show drun -show-icons")},
            **pill(colors_list[2]),
        ),
        widget.Spacer(length=8),
        extrawidget.Chord(
            fontsize=25,
            foreground=colors_list[3],
            fmt=" {}",
            padding=8,
        ),
        extrawidget.GroupBox(
            fontsize=39,
            margin_y=5,
            margin_x=16,
            padding_y=0,
            padding_x=6,
            borderwidth=4,
            active=colors_list[3],
            inactive=colors_list[9],
            rounded=True,
            highlight_color=colors_list[2],
            highlight_method="line",
            this_current_screen_border=colors_list[5],
            this_screen_border=colors_list[8],
            other_current_screen_border=colors_list[5],
            other_screen_border=colors_list[8],
            urgent_alert_method="line",
            urgent_border=colors_list[6],
            disable_drag=True,
            **pill(colors_list[2], radius=12),
        ),
        widget.Spacer(length=8),
        extrawidget.CurrentLayoutIcon(
            custom_icon_paths=["~/.config/qtile/icons/layout/"],
            scale=1.1,
            padding=0,
            **pill(colors_list[2]),
        ),
        widget.Spacer(length=8),
        extrawidget.WindowCount(
            fmt=" [{}]",
            fontsize=25,
            foreground=colors_list[9],
            padding=4,
        ),
        extrawidget.WindowName(
            foreground=colors_list[6],
            max_chars=45,
            padding=12,
            fontsize=25,
        ),
        widget.Spacer(length=bar.STRETCH),
        extrawidget.Clock(
            format="  %a %d %b   %H:%M  ",
            fontsize=33,
            foreground=colors_list[2],
            padding=0,
            mouse_callbacks={
                "Button1": lambda: qtile.cmd_spawn(
                    myTerm + " --class gcal-float -e calcurse"
                ),
            },
            **pill(colors_list[6], radius=12),
        ),
        widget.Spacer(length=bar.STRETCH),
        extrawidget.WidgetBox(
            text_closed="  SYS ",
            text_open="  SYS ",
            fontsize=28,
            foreground=colors_list[8],
            close_button_location="right",
            **pill(colors_list[3]),
            widgets=[
                extrawidget.CPU(
                    format="  {load_percent:>4}%",
                    fontsize=28,
                    foreground=colors_list[4],
                    update_interval=3,
                    padding=8,
                    mouse_callbacks={"Button1": lambda: qtile.cmd_spawn(myTerm + " -e htop")},
                ),
                extrawidget.Memory(
                    format="  {MemUsed:.0f}{mm}",
                    fontsize=28,
                    foreground=colors_list[8],
                    measure_mem="M",
                    update_interval=3,
                    padding=8,
                    mouse_callbacks={"Button1": lambda: qtile.cmd_spawn(myTerm + " -e htop")},
                ),
                extrawidget.ThermalSensor(
                    tag_sensor="Core 0",
                    fontsize=28,
                    foreground=colors_list[5],
                    foreground_alert=colors_list[3],
                    threshold=75,
                    fmt="  {}",
                    update_interval=5,
                    padding=8,
                ),
                extrawidget.NvidiaSensors(
                    format=" 󰍹  {temp}°C",
                    fontsize=28,
                    foreground=colors_list[5],
                    foreground_alert=colors_list[3],
                    threshold=80,
                    padding=8,
                ),
                extrawidget.DF(
                    partition="/",
                    format=" 󰋊  {uf}{m}",
                    fontsize=28,
                    foreground=colors_list[5],
                    visible_on_warn=False,
                    update_interval=60,
                    padding=8,
                ),
            ],
        ),
        widget.Spacer(length=4),
        extrawidget.WidgetBox(
            text_closed=" 󰎈 ",
            text_open=" 󰎈 ",
            fontsize=28,
            foreground=colors_list[7],
            close_button_location="right",
            **pill(colors_list[4]),
            widgets=[
                extrawidget.Mpris2(
                    name="browser",
                    objname="chromium",
                    format="{xesam:title} - {xesam:artist}",
                    fmt=" {} ",
                    fontsize=28,
                    max_chars=35,
                    foreground=colors_list[7],
                    paused_text=" {track}",
                    width=220,
                    scroll_fixed_width=True,
                    scroll=True,
                    padding=8,
                ),
            ],
        ),
        widget.Spacer(length=4),
        widget.Pomodoro(
            fontsize=26,
            color_active=colors_list[3],
            color_break=colors_list[4],
            color_inactive=colors_list[9],
            length_pomodori=25,
            length_short_break=5,
            length_long_break=15,
            num_pomodori=4,
            fmt=" {} ",
            prefix_inactive="󰔟 ",
            prefix_active="󱎫 ",
            prefix_break="󰒜 ",
            prefix_long_break="󰌪 ",
            prefix_paused="󰏤 ",
            notification_on=True,
            update_interval=1,
            **pill(colors_list[5]),
        ),
        widget.Spacer(length=4),
        extrawidget.GenPollText(
            func=get_keyboard_layout,
            update_interval=0.5,
            fontsize=28,
            foreground=colors_list[8],
            fmt="  {} ",
            padding=6,
            background=colors_list[0],
            decorations=[PowerLineDecoration(path="arrow_right", size=16)],
        ),
        extrawidget.Net(
            format=" 󰈀  {down:.0f}{down_suffix}↓ {up:.0f}{up_suffix}↑ ",
            fontsize=34,
            foreground=colors_list[9],
            update_interval=3,
            padding=6,
            background=colors_list[5],
            decorations=[PowerLineDecoration(path="arrow_right", size=16)],
        ),
        extrawidget.Volume(
            fmt="  {} ",
            fontsize=30,
            foreground=colors_list[8],
            step=5,
            padding=6,
            background=colors_list[2],
            mouse_callbacks={"Button3": lambda: qtile.cmd_spawn("pavucontrol")},
            decorations=[PowerLineDecoration(path="arrow_right", size=16)],
        ),
        extrawidget.Battery(
            format=" {char} {percent:2.0%} ",
            fontsize=24,
            charge_char="󰂄",
            discharge_char="󰁾",
            full_char="󰁹",
            empty_char="󰂃",
            low_foreground=colors_list[3],
            low_percentage=0.15,
            notify_below=15,
            foreground=colors_list[4],
            update_interval=30,
            padding=6,
            background=colors_list[8],
            decorations=[PowerLineDecoration(path="arrow_right", size=16)],
        ),
        widget.GenPollText(
            func=get_weather,
            update_interval=60,
            fontsize=38,
            foreground=colors_list[5],
            padding=6,
            background=colors_list[9],
            mouse_callbacks={
                "Button1": lambda: qtile.cmd_spawn(
                    myTerm + " --class weathr-float,weathr-float -o 'window.dimensions.columns=90' -o 'window.dimensions.lines=30' -e weathr"
                ),
            },
            decorations=[PowerLineDecoration(path="arrow_right", size=16)],
        ),
    ]

    if include_tray:
        widgets_list.extend([
            widget.Spacer(length=6, background=colors_list[0]),
            tray_widget(is_wayland),
            widget.Spacer(length=12),
        ])
    else:
        widgets_list.append(widget.Spacer(length=12))

    return widgets_list

def init_widgets_screen1(is_wayland=False):
    return init_widgets_list(include_tray=True, is_wayland=is_wayland)

def init_widgets_screen2(is_wayland=False):
    return init_widgets_list(include_tray=False, is_wayland=is_wayland)

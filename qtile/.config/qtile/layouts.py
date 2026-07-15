from libqtile import layout
from libqtile.config import Match

layout_theme = {
    "border_width": 3,
    "margin": 8,
}

monadtall_config = layout.MonadTall(
    **layout_theme,
    ratio=0.55,
    max_ratio=0.75,
    min_ratio=0.30,
    change_ratio=0.05,
    single_border_width=0,
    single_margin=0,
    new_client_position="after_current",
)

bsp_config = layout.Bsp(
    **layout_theme,
    fair=False,
    grow_amount=10,
    ratio=1.6,
    border_on_single=False,
    margin_on_single=0,
)

columns_config = layout.Columns(
    **layout_theme,
    num_columns=2,
    fair=False,
    insert_position=1,
    initial_ratio=1.2,
    border_on_single=False,
    border_focus_stack=None,
    border_normal_stack=None,
    wrap_focus_columns=True,
    wrap_focus_rows=True,
    split=True,
)

ratiotile_config = layout.RatioTile(
    **layout_theme,
    ratio=1.618,
    ratio_increment=0.1,
    fancy=True,
)

treetab_config = layout.TreeTab(
    font="Ubuntu Bold",
    fontsize=28,
    border_width=0,
    bg_color="#282c34e6",
    padding_left=16,
    padding_x=16,
    padding_y=12,
    sections=["MAIN", "SECONDARY", "OTHER"],
    section_fontsize=31,
    section_top=15,
    section_bottom=15,
    level_shift=8,
    vspace=3,
    panel_width=200,
)

monadthreecol_config = layout.MonadThreeCol(
    **layout_theme,
    ratio=0.45,
    main_centered=True,
    max_ratio=0.65,
    min_ratio=0.30,
    change_ratio=0.05,
    new_client_position="top",
    single_border_width=0,
    single_margin=0,
)

slice_config = layout.Slice(
    side="left",
    width=600,
    match=Match(wm_class="cmus"),
    fallback=layout.RatioTile(**layout_theme, ratio=1.618),
)

spiral_config = layout.Spiral(
    **layout_theme,
    main_pane="left",
    clockwise=True,
    ratio=0.618,
    ratio_increment=0.05,
    main_pane_ratio=0.55,
    new_client_position="top",
    border_on_single=False,
)

plasma_config = layout.Plasma(
    **layout_theme,
    border_width_single=0,
    fair=False,
)

zoomy_config = layout.Zoomy(**layout_theme)
floating_config = layout.Floating(**layout_theme)

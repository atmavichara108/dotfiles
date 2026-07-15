from libqtile.config import Group
from layouts import (
    monadtall_config, bsp_config, columns_config, ratiotile_config,
    treetab_config, monadthreecol_config, slice_config,
    spiral_config, plasma_config, zoomy_config, floating_config,
)

group_configs = [
    {"name": "1", "label": "ॐ", "layouts": [monadtall_config]},
    {"name": "2", "label": "श्री", "layouts": [bsp_config, columns_config]},
    {"name": "3", "label": "ह्रीं", "layouts": [treetab_config, ratiotile_config]},
    {"name": "4", "label": "क्लीं", "layouts": [monadthreecol_config, zoomy_config]},
    {"name": "5", "label": "ऐं", "layouts": [bsp_config, treetab_config]},
    {"name": "6", "label": "सौः", "layouts": [columns_config, plasma_config]},
    {"name": "7", "label": "हूं", "layouts": [plasma_config]},
    {"name": "8", "label": "रां", "layouts": [spiral_config, ratiotile_config]},
    {"name": "9", "label": "वं", "layouts": [slice_config]},
    {"name": "0", "label": "लं", "layouts": [floating_config]},
]

groups = [
    Group(
        name=conf["name"],
        label=conf["label"],
        layouts=conf["layouts"],
        layout=conf["layouts"][0].name,
    )
    for conf in group_configs
]

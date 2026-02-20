#!/bin/bash
WALLDIR="/home/rudra/.i3/wallpapers/"
WALL=$(find "$WALLDIR" -type f | shuf -n1)
feh --bg-fill "$WALL" --no-fehbg     # Без restore, сохрани в ~/.fehbg
echo "feh --bg-fill $WALL" >~/.fehbg # Для persistence
i3-msg reload

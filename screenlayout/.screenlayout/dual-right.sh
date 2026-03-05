#!/bin/bash
xrandr --dpi 192 \
  --fb 7680x2160 \
  --output eDP-1-1 --mode 3840x2160 --pos 0x0 --primary \
  --output DP-3 --mode 1920x1080 --rate 74.97 --scale 2x2 --pos 3840x0 --panning 3840x2160+3840+0

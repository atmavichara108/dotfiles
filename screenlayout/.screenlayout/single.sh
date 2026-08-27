#!/bin/bash
# Single monitor mode: disable external, reset framebuffer/panning to internal native.
xrandr --output DP-3 --off \
  --output eDP-1-1 --mode 3840x2160 --primary --dpi 192 \
  --fb 3840x2160 --panning 0x0

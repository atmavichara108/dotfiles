#!/bin/sh
# sddm-laptop-display.sh — SDDM DisplayCommand for laptop display setup
#
# Runs as root in SDDM context. DISPLAY and XAUTHORITY are provided by SDDM.
# Purpose: configure eDP-1-1 (laptop panel) as primary display before greeter.
#
# Constraints:
#   - POSIX sh only (no bash-isms)
#   - Read-only xrandr queries before any mutation
#   - Provider linking is NEVER performed automatically
#   - Does not invoke WM sessions, service managers, user display scripts,
#     Xorg config, or GPU switching tools
#   - Every potentially failing operation logged via logger -t sddm-laptop-display
#   - Any error exits 0 (never blocks SDDM), no sleep, reasons logged
#   - XAUTHORITY value is never logged

TAG="sddm-laptop-display"

log() {
    logger -t "$TAG" "$@"
}

fail() {
    logger -t "$TAG" "ERROR: $*"
    exit 0
}

# --- Environment validation ---
if [ -z "$DISPLAY" ]; then
    fail "DISPLAY is not set; cannot configure display"
fi
if [ -z "$XAUTHORITY" ]; then
    fail "XAUTHORITY is not set; cannot authenticate to X server"
fi
if ! command -v xrandr >/dev/null 2>&1; then
    fail "xrandr not found in PATH"
fi

log "start DISPLAY=$DISPLAY"

# --- Read-only discovery (no mutations before decision) ---
providers_out=$(xrandr --listproviders 2>&1) || fail "xrandr --listproviders failed"
query_out=$(xrandr --query 2>&1) || fail "xrandr --query failed"

log "providers: $(printf '%s' "$providers_out" | tr '\n' ' ')"

has_nvidia=0
has_modesetting=0
case "$providers_out" in
    *NVIDIA-0*) has_nvidia=1 ;;
esac
case "$providers_out" in
    *modesetting*) has_modesetting=1 ;;
esac
log "provider flags nvidia=$has_nvidia modesetting=$has_modesetting"

# --- eDP-1-1 detection ---
edp_connected=0
if printf '%s\n' "$query_out" | grep -q "eDP-1-1 connected"; then
    edp_connected=1
fi

if [ "$edp_connected" -eq 0 ]; then
    log "eDP-1-1 not connected or not visible in xrandr output"
    log "providers present: nvidia=$has_nvidia modesetting=$has_modesetting"
    log "reason: eDP-1-1 not visible; provider linking is never performed automatically"
    exit 0
fi

# --- eDP-1-1 is connected: configure ---
log "eDP-1-1 connected — by live RandR data eDP is already visible via linked modesetting provider; provider linking not required"

# Set native/preferred mode, primary, panning reset (no --fb, no --dpi)
cfg_out=$(xrandr \
    --output eDP-1-1 --auto --primary --panning 0x0 2>&1) || fail "xrandr configure eDP-1-1 failed: $cfg_out"
log "eDP-1-1 configured: auto primary panning=0x0"

# --- DP-3 handling ---
dp3_present=0
dp3_connected=0
if printf '%s\n' "$query_out" | grep -q "DP-3"; then
    dp3_present=1
fi
if printf '%s\n' "$query_out" | grep -q "DP-3 connected"; then
    dp3_connected=1
fi

if [ "$dp3_present" -eq 1 ]; then
    if [ "$dp3_connected" -eq 0 ]; then
        dp3_off_out=$(xrandr --output DP-3 --off 2>&1) || log "WARN: failed to disable disconnected DP-3: $dp3_off_out"
        log "DP-3 present and disconnected — disabled"
    else
        log "DP-3 connected — leaving mode/position/scale/primary untouched"
    fi
else
    log "DP-3 not present — no action"
fi

log "completed successfully"
exit 0

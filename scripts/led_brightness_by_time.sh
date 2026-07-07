#!/usr/bin/env bash
# Set DW LED brightness based on time of day.
# Intended to be run from cron every minute, e.g.:
#   * * * * * /Volumes/4TB\ SSD/projects/dune-weaver/scripts/led_brightness_by_time.sh >> /tmp/dw-led-brightness.log 2>&1
#
# Anchors below are (HH:MM, brightness 0-100). Brightness is linearly
# interpolated between consecutive anchors, so the LEDs ramp smoothly.

set -euo pipefail

API="${DW_API:-http://localhost:8080}"
ENDPOINT="$API/api/dw_leds/brightness"

# Edit these to taste. Must be sorted by time. First and last bracket midnight.
ANCHORS=(
  "00:00 5"    # deep night: dim glow
  "06:30 15"   # pre-dawn: warm wake-up level
  "08:00 60"   # morning: full ambient
  "12:00 90"   # midday peak
  "18:00 70"   # evening
  "21:30 30"   # wind-down
  "23:30 5"    # back to deep night
)

now_minutes() {
  local h m
  h=$(date +%H)
  m=$(date +%M)
  # base-10 force avoids "08" being parsed as octal
  echo $(( 10#$h * 60 + 10#$m ))
}

anchor_minutes() { # "HH:MM <bri>" -> minutes
  local t=${1%% *}
  local h=${t%%:*}
  local m=${t##*:}
  echo $(( 10#$h * 60 + 10#$m ))
}

anchor_value() { echo "${1##* }"; }

compute_brightness() {
  local now=$1 prev_t prev_v next_t next_v
  for ((i = 0; i < ${#ANCHORS[@]} - 1; i++)); do
    prev_t=$(anchor_minutes "${ANCHORS[i]}")
    next_t=$(anchor_minutes "${ANCHORS[i+1]}")
    if (( now >= prev_t && now <= next_t )); then
      prev_v=$(anchor_value "${ANCHORS[i]}")
      next_v=$(anchor_value "${ANCHORS[i+1]}")
      # linear interpolation, integer math
      echo $(( prev_v + (next_v - prev_v) * (now - prev_t) / (next_t - prev_t) ))
      return
    fi
  done
  # fallback: last anchor's value
  anchor_value "${ANCHORS[-1]}"
}

main() {
  local now bri
  now=$(now_minutes)
  bri=$(compute_brightness "$now")

  echo "[$(date -Iseconds)] minute=$now brightness=$bri"

  curl -fsS -X POST "$ENDPOINT" \
    -H 'Content-Type: application/json' \
    -d "{\"value\": $bri}"
  echo
}

main "$@"

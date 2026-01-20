#!/bin/bash
#
# Update Watcher for Dune Weaver
#
# This script runs on the host machine and watches for update triggers
# from the Docker container. When a trigger is detected, it runs 'dw update'.
#
# The container signals an update by creating .update-trigger file in the
# mounted volume, which the host can see and act upon.
#

set -e

# Configuration
TRIGGER_FILE=""
INSTALL_DIR=""
LOG_PREFIX="[update-watcher]"

# Find dune-weaver directory (same logic as dw script)
find_install_dir() {
    if [[ -f "$HOME/dune-weaver/main.py" ]]; then
        echo "$HOME/dune-weaver"
    elif [[ -f "/home/pi/dune-weaver/main.py" ]]; then
        echo "/home/pi/dune-weaver"
    else
        echo ""
    fi
}

log() {
    echo "$LOG_PREFIX $(date '+%Y-%m-%d %H:%M:%S') $1"
}

# Initialize
INSTALL_DIR=$(find_install_dir)
if [[ -z "$INSTALL_DIR" ]]; then
    log "ERROR: Dune Weaver installation not found"
    exit 1
fi

TRIGGER_FILE="$INSTALL_DIR/.update-trigger"
log "Watching for update triggers at: $TRIGGER_FILE"
log "Install directory: $INSTALL_DIR"

# Main watch loop
while true; do
    if [[ -f "$TRIGGER_FILE" ]]; then
        log "Update trigger detected!"

        # Read any message from trigger file (optional metadata)
        if [[ -s "$TRIGGER_FILE" ]]; then
            log "Trigger message: $(cat "$TRIGGER_FILE")"
        fi

        # Remove trigger file before update to prevent re-triggering
        rm -f "$TRIGGER_FILE"

        # Run the update
        log "Starting update process..."
        cd "$INSTALL_DIR"

        if /usr/local/bin/dw update 2>&1 | while read -r line; do log "$line"; done; then
            log "Update completed successfully"
        else
            log "Update completed with errors (exit code: $?)"
        fi

        log "Resuming watch..."
    fi

    # Poll every 2 seconds
    sleep 2
done

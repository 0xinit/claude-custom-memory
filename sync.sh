#!/usr/bin/env bash
#
# Claude Custom Memory — Bidirectional Sync
# Pulls latest from remote, runs daemon, commits and pushes if there are changes.
# Designed to run via cron on both Mac and Linux.
#
# Usage:
#   bash sync.sh              # full sync (pull → daemon → commit → push)
#   bash sync.sh --pull-only  # just pull (useful for manual refresh)
#
# Setup (one-time per machine):
#   cd ~/.claude/custom-memory
#   git init && git remote add origin https://github.com/0xinit/naruto-custom-memory.git
#   git push -u origin main
#
# Cron (every 4 hours):
#   0 */4 * * * bash ~/.claude/custom-memory/sync.sh >> /tmp/claude-memory-sync.log 2>&1
#
# SPDX-License-Identifier: MIT

set -euo pipefail

SYNC_DIR="$HOME/.claude/custom-memory"
DAEMON="$HOME/.claude/memory/memory-daemon.py"
DAEMON_CONF="$HOME/.claude/memory/memory.conf"
HOSTNAME=$(hostname -s)

PULL_ONLY=false
[[ "${1:-}" == "--pull-only" ]] && PULL_ONLY=true

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }

if [[ ! -d "$SYNC_DIR/.git" ]]; then
  log "ERROR: $SYNC_DIR is not a git repo. Run setup first."
  exit 1
fi

cd "$SYNC_DIR"

# Pull latest from remote
if git remote get-url origin &>/dev/null; then
  log "Pulling from remote..."
  git pull --rebase origin main 2>/dev/null || log "Pull failed (remote may not exist yet)"
else
  log "No remote configured, skipping pull"
fi

if $PULL_ONLY; then
  log "Pull-only mode, done."
  exit 0
fi

# Run daemon to generate fresh memory
if [[ -f "$DAEMON" ]]; then
  log "Running memory daemon..."
  python3 "$DAEMON" --config "$DAEMON_CONF" 2>&1 || log "Daemon returned non-zero"
fi

# Check for changes
git add -A

if git diff --cached --quiet; then
  log "No changes to sync."
  exit 0
fi

# Commit with machine identifier
CHANGED=$(git diff --cached --stat | tail -1)
git commit -m "sync($HOSTNAME): $CHANGED" --quiet

# Push to remote
if git remote get-url origin &>/dev/null; then
  log "Pushing to remote..."
  git push origin main --quiet 2>/dev/null || log "Push failed (check auth)"
fi

log "Sync complete."

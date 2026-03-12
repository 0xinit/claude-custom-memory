#!/usr/bin/env bash
#
# Claude Custom Memory — Installer
# Sets up memory daemon, skills, and cron job.
#
# Supports two install modes:
#   1. Clone:  git clone ... && bash install.sh
#   2. Curl:   curl -fsSL https://raw.githubusercontent.com/0xinit/claude-custom-memory/main/install.sh | bash
#
# Usage: bash install.sh [--interval HOURS]
#
# SPDX-License-Identifier: MIT

set -euo pipefail

CLAUDE_DIR="$HOME/.claude"
MEMORY_DIR="$CLAUDE_DIR/memory"
SKILLS_DIR="$CLAUDE_DIR/skills"
REPO_URL="https://raw.githubusercontent.com/0xinit/claude-custom-memory/main"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }
header(){ echo -e "\n${BOLD}$1${NC}"; }

# Detect install mode: local clone or remote curl
IS_LOCAL=false
SCRIPT_DIR=""
if [[ -n "${BASH_SOURCE[0]:-}" ]] && [[ "${BASH_SOURCE[0]}" != "bash" ]]; then
  CANDIDATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd)"
  if [[ -f "$CANDIDATE/memory-daemon.py" ]]; then
    IS_LOCAL=true
    SCRIPT_DIR="$CANDIDATE"
  fi
fi

fetch_file() {
  local rel_path="$1"
  local dest="$2"

  if $IS_LOCAL; then
    cp "$SCRIPT_DIR/$rel_path" "$dest"
  else
    if ! curl -fsSL "$REPO_URL/$rel_path" -o "$dest"; then
      error "Failed to download $rel_path"
      exit 1
    fi
  fi
}

INTERVAL_HOURS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interval)
      INTERVAL_HOURS="$2"
      shift 2
      ;;
    --interval=*)
      INTERVAL_HOURS="${1#*=}"
      shift
      ;;
    -h|--help)
      echo "Usage: bash install.sh [--interval HOURS]"
      echo ""
      echo "Options:"
      echo "  --interval HOURS  Set cron interval (default: from memory.conf, fallback 1)"
      echo "  -h, --help        Show this help"
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      exit 1
      ;;
  esac
done

# --- Prerequisites ---

header "Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
  error "python3 is required but not installed."
  exit 1
fi
info "python3 found"

if ! command -v crontab &>/dev/null; then
  error "crontab is required but not available."
  exit 1
fi
info "crontab available"

if ! $IS_LOCAL && ! command -v curl &>/dev/null; then
  error "curl is required for remote install."
  exit 1
fi

if [[ ! -d "$CLAUDE_DIR" ]]; then
  error "~/.claude/ not found. Is Claude Code installed?"
  exit 1
fi
info "~/.claude/ exists"

if $IS_LOCAL; then
  info "Install mode: local (cloned repo)"
else
  info "Install mode: remote (downloading from GitHub)"
fi

# --- Read config for interval ---

if [[ -z "$INTERVAL_HOURS" ]]; then
  if $IS_LOCAL && [[ -f "$SCRIPT_DIR/memory.conf" ]]; then
    INTERVAL_HOURS=$(grep -E "^interval_hours=" "$SCRIPT_DIR/memory.conf" | cut -d= -f2 | tr -d ' ' || echo "1")
  fi
  INTERVAL_HOURS="${INTERVAL_HOURS:-1}"
fi

if ! [[ "$INTERVAL_HOURS" =~ ^[0-9]+$ ]] || [[ "$INTERVAL_HOURS" -lt 1 ]]; then
  error "Invalid interval: $INTERVAL_HOURS (must be a positive integer)"
  exit 1
fi

# --- Create directories ---

header "Setting up directories..."

mkdir -p "$MEMORY_DIR"
mkdir -p "$MEMORY_DIR/.session-cache"
mkdir -p "$SKILLS_DIR/custom-memory"
mkdir -p "$SKILLS_DIR/important"
info "Created directories"

# --- Install files ---

header "Installing files..."

fetch_file "memory-daemon.py" "$MEMORY_DIR/memory-daemon.py"
chmod +x "$MEMORY_DIR/memory-daemon.py"
info "Installed memory-daemon.py"

fetch_file "memory.conf" "$MEMORY_DIR/memory.conf"
info "Installed memory.conf"

fetch_file "memory-status.py" "$MEMORY_DIR/memory-status.py"
chmod +x "$MEMORY_DIR/memory-status.py"
info "Installed memory-status.py"

# --- Install skills ---

header "Installing skills..."

fetch_file "skills/custom-memory/SKILL.md" "$SKILLS_DIR/custom-memory/SKILL.md"
info "Installed /custom-memory skill"

fetch_file "skills/important/SKILL.md" "$SKILLS_DIR/important/SKILL.md"
info "Installed /important skill"

# --- Set up cron ---

header "Setting up cron job (every ${INTERVAL_HOURS}h)..."

CRON_CMD="python3 $MEMORY_DIR/memory-daemon.py --config $MEMORY_DIR/memory.conf"
CRON_MARKER="# claude-custom-memory"

EXISTING_CRON=$(crontab -l 2>/dev/null || true)

if [[ "$INTERVAL_HOURS" -eq 1 ]]; then
  CRON_SCHEDULE="0 * * * *"
else
  CRON_SCHEDULE="0 */${INTERVAL_HOURS} * * *"
fi

if echo "$EXISTING_CRON" | grep -qF "$CRON_MARKER"; then
  NEW_CRON=$(echo "$EXISTING_CRON" | grep -vF "$CRON_MARKER")
  NEW_CRON="${NEW_CRON}
${CRON_SCHEDULE} ${CRON_CMD} ${CRON_MARKER}"
  echo "$NEW_CRON" | crontab -
  info "Updated existing cron entry"
else
  (echo "$EXISTING_CRON"; echo "${CRON_SCHEDULE} ${CRON_CMD} ${CRON_MARKER}") | crontab -
  info "Added cron entry"
fi

# --- Verify ---

header "Verifying installation..."

ERRORS=0

[[ -f "$MEMORY_DIR/memory-daemon.py" ]] && info "memory-daemon.py ✓" || { error "memory-daemon.py missing"; ERRORS=$((ERRORS+1)); }
[[ -f "$MEMORY_DIR/memory.conf" ]] && info "memory.conf ✓" || { error "memory.conf missing"; ERRORS=$((ERRORS+1)); }
[[ -f "$MEMORY_DIR/memory-status.py" ]] && info "memory-status.py ✓" || { warn "memory-status.py not installed"; }
[[ -f "$SKILLS_DIR/custom-memory/SKILL.md" ]] && info "/custom-memory skill ✓" || { warn "/custom-memory skill not installed"; }
[[ -f "$SKILLS_DIR/important/SKILL.md" ]] && info "/important skill ✓" || { warn "/important skill not installed"; }

if crontab -l 2>/dev/null | grep -qF "$CRON_MARKER"; then
  info "Cron job active ✓"
else
  error "Cron job not found"
  ERRORS=$((ERRORS+1))
fi

# --- Summary ---

header "Installation complete!"
echo ""
echo "  Installed to:  $MEMORY_DIR"
echo "  Cron interval: every ${INTERVAL_HOURS} hour(s)"
echo "  Config:        $MEMORY_DIR/memory.conf"
echo ""
echo "  What was installed:"
echo "    ~/.claude/memory/memory-daemon.py   — cron daemon"
echo "    ~/.claude/memory/memory-status.py   — status dashboard"
echo "    ~/.claude/memory/memory.conf        — configuration"
echo "    ~/.claude/skills/custom-memory/     — /custom-memory skill"
echo "    ~/.claude/skills/important/         — /important skill"
echo ""
echo "  Usage in Claude Code:"
echo "    /custom-memory load short    — recent work (rolling window)"
echo "    /custom-memory load long     — full history"
echo "    /custom-memory load important— user-flagged moments"
echo "    /important                   — flag current context"
echo ""
echo "  Manual commands:"
echo "    python3 $MEMORY_DIR/memory-daemon.py              # run now"
echo "    python3 $MEMORY_DIR/memory-daemon.py --status     # check status"
echo "    python3 $MEMORY_DIR/memory-daemon.py --important  # flag important"
echo "    python3 $MEMORY_DIR/memory-status.py              # dashboard"
echo "    python3 $MEMORY_DIR/memory-status.py -p <name>    # project detail"
echo ""

if [[ "$ERRORS" -gt 0 ]]; then
  error "$ERRORS error(s) during installation"
  exit 1
fi

echo "  To uninstall:"
echo "    crontab -l | grep -v 'claude-custom-memory' | crontab -"
echo "    rm -rf $MEMORY_DIR"
echo "    rm -rf $SKILLS_DIR/custom-memory $SKILLS_DIR/important"
echo ""

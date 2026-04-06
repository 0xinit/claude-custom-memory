#!/usr/bin/env bash
#
# Linux Setup Script for Claude Custom Memory + Project Sync
# Run this AFTER copying .claude/ and web3_projects/ from the T7 drive.
#
# Usage:
#   1. Mount T7 drive
#   2. cp -a /media/naruto/T7/mac_linux_sync/.claude ~/
#   3. cp -a /media/naruto/T7/mac_linux_sync/web3_projects ~/web3projects
#   4. bash ~/linux-setup.sh
#
# Adjust T7 mount path if different — check with: ls /media/naruto/

set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1"; }

# --- Prerequisites ---
echo -e "${BOLD}Checking prerequisites...${NC}"

command -v git &>/dev/null || { error "git not installed. Run: sudo apt install git"; exit 1; }
command -v python3 &>/dev/null || { error "python3 not installed. Run: sudo apt install python3"; exit 1; }
info "git and python3 found"

[[ -d "$HOME/.claude" ]] || { error "~/.claude not found. Copy it from T7 first."; exit 1; }
info "~/.claude exists"

# --- Replace custom-memory with git clone ---
echo -e "\n${BOLD}Setting up sync repo...${NC}"

if [[ -d "$HOME/.claude/custom-memory/.git" ]]; then
  info "custom-memory is already a git repo, pulling latest"
  cd "$HOME/.claude/custom-memory" && git pull --rebase origin main 2>/dev/null || true
else
  rm -rf "$HOME/.claude/custom-memory"
  git clone https://github.com/0xinit/naruto-custom-memory.git "$HOME/.claude/custom-memory"
  info "Cloned naruto-custom-memory"
fi

# --- Create symlinks ---
echo -e "\n${BOLD}Creating symlinks...${NC}"

cd "$HOME/.claude"

for item in skills rules hooks todos transcripts CLAUDE.md settings.json; do
  rm -rf "$item"
  ln -s "$HOME/.claude/custom-memory/$item" "$item"
  info "Linked $item"
done

# --- Symlink global memory files ---
echo -e "\n${BOLD}Linking global memory files...${NC}"

mkdir -p "$HOME/.claude/memory"
cd "$HOME/.claude/memory"

for f in memory-daemon.py memory-status.py memory.conf long-memory.md short-memory.md .daemon-state.json; do
  rm -f "$f"
  ln -s "$HOME/.claude/custom-memory/global-memory/$f" "$f"
  info "Linked memory/$f"
done

# --- Add cron jobs ---
echo -e "\n${BOLD}Setting up cron jobs...${NC}"

EXISTING_CRON=$(crontab -l 2>/dev/null || true)

DAEMON_CRON="0 * * * * python3 $HOME/.claude/memory/memory-daemon.py --config $HOME/.claude/memory/memory.conf >> /tmp/claude-memory-daemon.log 2>&1 # claude-custom-memory"
SYNC_CRON="0 */4 * * * bash $HOME/.claude/custom-memory/sync.sh >> /tmp/claude-memory-sync.log 2>&1 # claude-memory-sync"

NEW_CRON="$EXISTING_CRON"

if ! echo "$EXISTING_CRON" | grep -qF "claude-custom-memory"; then
  NEW_CRON="${NEW_CRON}
${DAEMON_CRON}"
  info "Added daemon cron (every 1h)"
else
  info "Daemon cron already exists"
fi

if ! echo "$EXISTING_CRON" | grep -qF "claude-memory-sync"; then
  NEW_CRON="${NEW_CRON}
${SYNC_CRON}"
  info "Added sync cron (every 4h)"
else
  info "Sync cron already exists"
fi

echo "$NEW_CRON" | crontab -

# --- Verify ---
echo -e "\n${BOLD}Verifying...${NC}"

python3 "$HOME/.claude/memory/memory-daemon.py" --status 2>&1 | head -5
echo ""
python3 "$HOME/.claude/memory/memory-status.py" 2>&1 | head -15
echo ""
bash "$HOME/.claude/custom-memory/sync.sh" 2>&1

echo -e "\n${BOLD}Setup complete!${NC}"
echo "  Sync repo: ~/.claude/custom-memory/"
echo "  Daemon: runs every 1h"
echo "  Sync: runs every 4h (bidirectional)"
echo "  Dashboard: python3 ~/.claude/memory/memory-status.py"

# Claude Custom Memory

Persistent long-term and short-term memory for Claude Code sessions.

A cron-powered daemon that reads your Claude Code transcripts and maintains structured memory files — so Claude can recall past work, decisions, and context across sessions.

## How It Works

```
┌─────────────┐     cron      ┌──────────────────┐     writes     ┌─────────────────┐
│   Claude     │ ──────────── │  memory-daemon.py │ ────────────── │  ~/.claude/      │
│   Transcripts│   (hourly)   │                   │                │  memory/         │
│   (.jsonl)   │              │  Parses sessions  │                │  ├─ long.md      │
└─────────────┘              │  Extracts context  │                │  ├─ short.md     │
                              └──────────────────┘                │  └─ important.md │
                                                                   └─────────────────┘
                                                                          │
                                                                    /custom-memory
                                                                    /important
                                                                          │
                                                                   ┌──────────────┐
                                                                   │  Claude Code  │
                                                                   │  (next session)│
                                                                   └──────────────┘
```

## Install

```bash
git clone https://github.com/YOUR_USERNAME/claude-custom-memory.git
cd claude-custom-memory
bash install.sh
```

Set a custom cron interval:

```bash
bash install.sh --interval 2  # every 2 hours
```

## Usage

### Load memory in Claude Code

```
/custom-memory load short      # recent work (last 3 hours)
/custom-memory load long       # full history
/custom-memory load important  # user-flagged moments
/custom-memory load all        # everything
/custom-memory status          # daemon status
/custom-memory refresh         # manually trigger daemon
```

### Flag important context

```
/important       # flag last 10 messages
/important 20    # flag last 20 messages
```

Use `/important` after key decisions, solved bugs, deployments, or anything you want to recall later.

### Manual commands

```bash
# Run daemon manually
python3 ~/.claude/memory/memory-daemon.py

# Check status
python3 ~/.claude/memory/memory-daemon.py --status

# Flag important from CLI
python3 ~/.claude/memory/memory-daemon.py --important --n 15
```

## Memory Stores

| Store | File | Retention | Content |
|-------|------|-----------|---------|
| **Long** | `long-memory.md` | 500 entries (configurable) | All sessions, append-only |
| **Short** | `short-memory.md` | Rolling 3h (configurable) | Recent work only |
| **Important** | `important.md` | Permanent | User-flagged via `/important` |

Each entry contains:
- Timestamp and project name
- User requests (truncated)
- Key assistant responses (truncated)
- Files changed
- Tools used with counts

## Configuration

Edit `~/.claude/memory/memory.conf`:

```ini
# Cron interval (hours)
interval_hours=1

# Short memory window (hours)
short_memory_hours=3

# Max long memory entries before pruning
long_memory_max_entries=500

# AI summarization (requires ANTHROPIC_API_KEY)
summarize=false
```

After changing `interval_hours`, re-run `bash install.sh` to update the cron schedule.

## Uninstall

```bash
# Remove cron job
crontab -l | grep -v 'claude-custom-memory' | crontab -

# Remove files
rm -rf ~/.claude/memory
rm -rf ~/.claude/skills/custom-memory ~/.claude/skills/important
```

## File Structure

```
claude-custom-memory/
├── memory-daemon.py              # Main daemon script
├── memory.conf                   # Default configuration
├── install.sh                    # Installer with cron setup
├── skills/
│   ├── custom-memory/SKILL.md    # /custom-memory skill
│   └── important/SKILL.md        # /important skill
└── README.md
```

## Requirements

- Claude Code CLI installed
- Python 3.6+
- cron (macOS/Linux)

## License

MIT

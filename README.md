# Claude Custom Memory

Persistent long-term and short-term memory for Claude Code sessions.

A cron-powered daemon that reads your Claude Code transcripts and maintains structured memory files — project-scoped by default, with global cross-project memory available.

## How It Works

```
┌──────────────┐            ┌────────────────────┐            ┌─────────────────────────────┐
│ Claude       │    cron    │ memory-daemon.py   │   writes   │ Per-project:                │
│ Transcripts  │ ─────────► │                    │ ────────►  │ myproject/                  │
│ (.jsonl)     │  (hourly)  │ Groups by project  │            │ └─ myproject-memory/        │
└──────────────┘            │ Writes per-project │            │    ├─ myproject-long.md     │
                            │ Writes global      │            │    └─ myproject-short.md    │
                            └────────────────────┘            │                             │
                                                              │ Global:                     │
                                                              │ ~/.claude/memory/           │
                                                              │ ├─ long-memory.md           │
                                                              │ └─ short-memory.md          │
                                                              └─────────────────────────────┘
```

## Install

**One-liner** (no clone needed):

```bash
curl -fsSL https://raw.githubusercontent.com/0xinit/claude-custom-memory/main/install.sh | bash
```

With a custom cron interval:

```bash
curl -fsSL https://raw.githubusercontent.com/0xinit/claude-custom-memory/main/install.sh | bash -s -- --interval 2
```

**Or clone and install:**

```bash
git clone https://github.com/0xinit/claude-custom-memory.git
cd claude-custom-memory
bash install.sh
```

## What Gets Installed

```
~/.claude/
├── memory/
│   ├── memory-daemon.py          # cron daemon
│   ├── memory.conf               # configuration
│   ├── long-memory.md            # ← global, all projects (runtime)
│   ├── short-memory.md           # ← global, all projects (runtime)
│   └── important-memory.md       # ← global fallback (runtime)
└── skills/
    ├── custom-memory/SKILL.md    # /custom-memory skill
    └── important/SKILL.md        # /important skill
```

Per-project memory is written inside each project directory:

```
your-project/
└── your-project-memory/
    ├── your-project-long-memory.md
    ├── your-project-short-memory.md
    └── your-project-important-memory.md
```

Add `*-memory/` to your project's `.gitignore`.

## Usage

### Project memory (default)

```
/custom-memory load short       # this project's recent work
/custom-memory load long        # this project's full history
/custom-memory load important   # this project's flagged moments
/custom-memory load all         # all three for this project
```

### Global memory (all projects)

```
/custom-memory all load short      # recent work across all projects
/custom-memory all load long       # full history across all projects
/custom-memory all load important  # flagged moments across all projects
```

### Flag important context

```
/important       # flag last 10 messages for this project
/important 20    # flag last 20 messages
```

Use `/important` after key decisions, solved bugs, deployments, or anything you want to recall later.

### Other commands

```
/custom-memory status    # daemon status, project + global sizes
/custom-memory refresh   # manually trigger daemon
```

### Manual CLI commands

```bash
python3 ~/.claude/memory/memory-daemon.py              # run daemon now
python3 ~/.claude/memory/memory-daemon.py --status      # check status
python3 ~/.claude/memory/memory-daemon.py --important   # flag important
```

## Memory Stores

| Store | Scope | Retention | Content |
|-------|-------|-----------|---------|
| **Long** | Per-project + global | 500 entries (configurable) | All sessions, append-only |
| **Short** | Per-project + global | Rolling 3h (configurable) | Recent work only |
| **Important** | Per-project (fallback global) | Permanent | User-flagged via `/important` |

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

After changing `interval_hours`, re-run the installer to update the cron schedule.

## Uninstall

```bash
# Remove cron job
crontab -l | grep -v 'claude-custom-memory' | crontab -

# Remove global files
rm -rf ~/.claude/memory
rm -rf ~/.claude/skills/custom-memory ~/.claude/skills/important

# Remove project memory dirs (in each project)
rm -rf <project-dir>/<project-name>-memory
```

## Requirements

- Claude Code CLI installed
- Python 3.6+
- cron (macOS/Linux)
- curl (for one-liner install only)

## License

MIT

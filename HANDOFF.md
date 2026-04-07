# Claude Custom Memory — Mac to Linux Migration Handoff

## What Was Done (on Mac)

### 1. Fixed memory-daemon.py bugs
- Added `PermissionError` handling for macOS TCC (cron can't access ~/Desktop)
- Added `encoding="utf-8", errors="replace"` in `parse_transcript()` for non-UTF-8 transcript files
- Removed `ensure_gitignore()` function (no longer needed)

### 2. Centralized project memory
**Before:** Memory was scattered in each project repo at `<project-dir>/<project-name>-memory/`
**After:** All project memory lives at `~/.claude/custom-memory/projects/<name>/`

Files changed:
- `memory-daemon.py` — writes to `~/.claude/custom-memory/projects/<name>/` via `PROJECT_MEMORY_DIR` constant
- `memory-status.py` — scans `~/.claude/custom-memory/projects/` instead of project dirs
- `skills/custom-memory/SKILL.md` — updated read paths
- `skills/important/SKILL.md` — updated write paths, removed `--project-dir` param
- `install.sh` — creates `~/.claude/custom-memory/projects/` dir
- `migrate.sh` — one-time script that moved all 37 old `*-memory/` dirs to centralized location (already run on Mac)

### 3. Created bidirectional sync system
- Private GitHub repo: `0xinit/naruto-custom-memory` (HTTPS, not SSH)
- `sync.sh` — pulls from remote, runs daemon, commits if changes, pushes. Runs via cron every 4 hours on both machines.
- Repo lives at `~/.claude/custom-memory/` and is the source of truth for synced files.

### 4. Symlinked shared config into sync repo (on Mac)
These files/dirs were MOVED into `~/.claude/custom-memory/` and symlinked back:

| Symlink | Points to |
|---------|-----------|
| `~/.claude/skills` | `~/.claude/custom-memory/skills` |
| `~/.claude/rules` | `~/.claude/custom-memory/rules` |
| `~/.claude/hooks` | `~/.claude/custom-memory/hooks` |
| `~/.claude/todos` | `~/.claude/custom-memory/todos` |
| `~/.claude/transcripts` | `~/.claude/custom-memory/transcripts` |
| `~/.claude/CLAUDE.md` | `~/.claude/custom-memory/CLAUDE.md` |
| `~/.claude/settings.json` | `~/.claude/custom-memory/settings.json` |

Global memory files symlinked:

| Symlink | Points to |
|---------|-----------|
| `~/.claude/memory/memory-daemon.py` | `~/.claude/custom-memory/global-memory/memory-daemon.py` |
| `~/.claude/memory/memory-status.py` | `~/.claude/custom-memory/global-memory/memory-status.py` |
| `~/.claude/memory/memory.conf` | `~/.claude/custom-memory/global-memory/memory.conf` |
| `~/.claude/memory/long-memory.md` | `~/.claude/custom-memory/global-memory/long-memory.md` |
| `~/.claude/memory/short-memory.md` | `~/.claude/custom-memory/global-memory/short-memory.md` |
| `~/.claude/memory/.daemon-state.json` | `~/.claude/custom-memory/global-memory/.daemon-state.json` |

### 5. Cron jobs on Mac
```
0 * * * *   python3 ~/.claude/memory/memory-daemon.py --config ~/.claude/memory/memory.conf >> /tmp/claude-memory-daemon.log 2>&1
0 */4 * * * bash ~/.claude/custom-memory/sync.sh >> /tmp/claude-memory-sync.log 2>&1
```

### 6. Copied files to Linux via tarball + Google Drive
- `dot-claude.tar.gz` — full `~/.claude/` + `~/.claude.json`
- `web3-projects.tar.gz` — all projects with `.git/` history, `.env` files, excluding build artifacts and project-anya

### 7. Ran linux-setup.sh on Linux
The script (`linux-setup.sh` in the claude-custom-memory repo) was run. It:
- Cloned `naruto-custom-memory` to `~/.claude/custom-memory/`
- Created all symlinks listed above
- Added both cron jobs
- Verification passed

---

## What Still Needs To Be Done (on Linux)

### 1. Clean macOS resource fork junk from projects
```bash
cd ~/Desktop/web3projects
find . -name '._*' -delete
find . -name '.DS_Store' -delete
```

### 2. Map Mac transcript paths to Linux paths for Claude's built-in memory
Claude's built-in memory is stored at `~/.claude/projects/<encoded-path>/memory/`. The paths are Mac-encoded:
```
~/.claude/projects/-Users-naruto-Desktop-web3_projects-rasenganfi/memory/
```
But on Linux, Claude looks for:
```
~/.claude/projects/-home-naruto-Desktop-web3projects-rasenganfi/memory/
```

**Need a script that:**
1. Scans all `~/.claude/projects/-Users-naruto-Desktop-web3_projects-*/memory/` dirs
2. Extracts the project name from each
3. Creates the Linux-encoded equivalent dir: `~/.claude/projects/-home-naruto-Desktop-web3projects-<name>/memory/`
4. Copies the memory files (MEMORY.md and individual .md files) into the new dir

This is the only way to preserve Claude's built-in memory (user preferences, feedback, project context) across machines.

### 3. Fix cron job path for memory daemon
The cron job references `~/.claude/memory/memory-daemon.py` which is a symlink to `~/.claude/custom-memory/global-memory/memory-daemon.py`. Verify this symlink works:
```bash
python3 ~/.claude/memory/memory-daemon.py --status
```

### 4. Verify sync works end-to-end
```bash
bash ~/.claude/custom-memory/sync.sh
```
Should show: pull → daemon runs → commit if changes → push.

### 5. (Optional) Push 7 repos that have no GitHub remote
These repos have local git history but no remote. They exist only on the Mac and now Linux:
- ClawX
- dynamic-mpp
- malClaw
- polyaave
- price-tracker
- threadguy-calls
- vegas-world

To preserve them, create GitHub repos and push from Linux.

---

## Architecture Overview

```
~/.claude/
├── custom-memory/              ← git repo (0xinit/naruto-custom-memory), syncs every 4h
│   ├── projects/               ← daemon-generated project memory
│   │   ├── rasenganfi/
│   │   │   ├── rasenganfi-long-memory.md
│   │   │   ├── rasenganfi-short-memory.md
│   │   │   └── rasenganfi-important-memory.md
│   │   └── ...
│   ├── global-memory/          ← daemon scripts + global memory files
│   │   ├── memory-daemon.py
│   │   ├── memory-status.py
│   │   ├── memory.conf
│   │   ├── long-memory.md
│   │   ├── short-memory.md
│   │   └── .daemon-state.json
│   ├── claude-memory/          ← copy of Claude's built-in memory per project
│   ├── skills/
│   ├── rules/
│   ├── hooks/
│   ├── todos/
│   ├── transcripts/
│   ├── CLAUDE.md
│   ├── settings.json
│   └── sync.sh
├── memory/                     ← symlinks to custom-memory/global-memory/
├── skills → custom-memory/skills
├── rules → custom-memory/rules
├── hooks → custom-memory/hooks
├── todos → custom-memory/todos
├── transcripts → custom-memory/transcripts
├── CLAUDE.md → custom-memory/CLAUDE.md
├── settings.json → custom-memory/settings.json
└── projects/                   ← Claude's built-in data (transcripts, memory)
    └── -Users-naruto-Desktop-web3_projects-*/
        ├── *.jsonl             ← conversation transcripts (machine-specific)
        └── memory/             ← Claude's built-in memory (needs path mapping)

~/Desktop/web3projects/         ← Linux project path (Mac: ~/Desktop/web3_projects/)
```

## Key Differences Between Machines

| | Mac | Linux |
|---|---|---|
| Projects path | `~/Desktop/web3_projects/` | `~/Desktop/web3projects/` |
| Home dir | `/Users/naruto` | `/home/naruto` |
| Claude transcript encoding | `-Users-naruto-Desktop-web3_projects-*` | `-home-naruto-Desktop-web3projects-*` |
| Python | system python3 (3.9) | system python3 |
| GitHub auth | HTTPS via gh | HTTPS via gh |

## Repo: 0xinit/claude-custom-memory
Contains the source code for:
- `memory-daemon.py`
- `memory-status.py`
- `memory.conf`
- `install.sh`
- `migrate.sh`
- `linux-setup.sh`
- `sync.sh`
- `skills/custom-memory/SKILL.md`
- `skills/important/SKILL.md`

## Repo: 0xinit/naruto-custom-memory (PRIVATE)
The actual sync repo that lives at `~/.claude/custom-memory/`. Contains all synced files.

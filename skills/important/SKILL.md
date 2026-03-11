---
name: important
description: "Flag the last N messages as important for the current project. Saves to project-scoped memory."
---

# Flag Important Context

When the user invokes `/important`, extract and persist critical context to the current project's memory.

## Behavior

1. Determine the current project name from the working directory
2. Run the memory daemon's important extractor:

```bash
python3 ~/.claude/memory/memory-daemon.py --important --project-dir "$(pwd)" --n 10
```

If you have access to the transcript path, pass it:

```bash
python3 ~/.claude/memory/memory-daemon.py --important --transcript "$TRANSCRIPT_PATH" --project-dir "$(pwd)" --n 10
```

3. Confirm to the user what was saved and where

## Arguments

- `/important` — flag last 10 messages
- `/important 20` — flag last 20 messages
- `/important 5` — flag last 5 messages

Parse the number from the argument and pass via `--n`.

## Where It Saves

Project-scoped (default):
```
<project-dir>/<project-name>-memory/<project-name>-important-memory.md
```

Falls back to global (`~/.claude/memory/important-memory.md`) if the project directory can't be determined.

## When to Use

- Key architectural decision made
- Hard bug solved
- Deployment details (addresses, chains, configs)
- User explicitly says "remember this" or "save this"

## After Flagging

Tell the user: "Use `/custom-memory load important` in a future session to recall this."

---
name: important
description: "Flag the last N messages in the current session as important for long-term recall. Use when the user wants to save critical context, decisions, or breakthroughs."
---

# Flag Important Context

When the user invokes `/important`, extract and persist the most critical recent context.

## Behavior

1. Determine the current session's transcript path from the environment or session context
2. Run the memory daemon's important extractor:

```bash
python3 ~/.claude/memory/memory-daemon.py --important --n 10
```

If you have access to the transcript path, pass it:

```bash
python3 ~/.claude/memory/memory-daemon.py --important --transcript "$TRANSCRIPT_PATH" --n 10
```

3. Confirm to the user what was saved

## Optional Arguments

The user can specify how many messages to flag:

- `/important` — default last 10 messages
- `/important 20` — last 20 messages
- `/important 5` — last 5 messages

Parse the number from the argument and pass it via `--n`.

## When to Use

- User made a key architectural decision
- A hard bug was solved and the user wants to remember the fix
- Important deployment details (addresses, chains, configs)
- User explicitly says "remember this" or "save this"

## What Gets Saved

The daemon extracts from the flagged messages:
- User requests (truncated to 300 chars)
- Assistant key responses (truncated to 500 chars)
- Files changed
- Tools used
- Timestamp and project name
- A "Flagged as important by user" marker

Saved to `~/.claude/memory/important.md`, newest first.

## Loading Important Memory Later

Tell the user: "Use `/custom-memory load important` in a future session to recall this."

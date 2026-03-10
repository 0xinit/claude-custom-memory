#!/usr/bin/env python3
"""
Claude Custom Memory Daemon
Extracts conversation context from Claude Code sessions and maintains
long-term and short-term memory files.

Run via cron or manually: python3 memory-daemon.py [--config path/to/memory.conf]

SPDX-License-Identifier: MIT
"""

import json
import os
import re
import sys
import glob
import time
import hashlib
import argparse
from datetime import datetime, timedelta
from pathlib import Path

MEMORY_DIR = Path.home() / ".claude" / "memory"
LONG_MEMORY = MEMORY_DIR / "long-memory.md"
SHORT_MEMORY = MEMORY_DIR / "short-memory.md"
IMPORTANT_MEMORY = MEMORY_DIR / "important.md"
SESSION_CACHE = MEMORY_DIR / ".session-cache"
STATE_FILE = MEMORY_DIR / ".daemon-state.json"

DEFAULT_CONFIG = {
    "interval_hours": 1,
    "short_memory_hours": 3,
    "long_memory_max_entries": 500,
    "summarize": False,
    "important_max_messages": 10,
}


def load_config(config_path=None):
    config = DEFAULT_CONFIG.copy()
    if config_path and os.path.exists(config_path):
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip()
                    if key in config:
                        if isinstance(config[key], bool):
                            config[key] = val.lower() in ("true", "1", "yes")
                        elif isinstance(config[key], int):
                            config[key] = int(val)
                        else:
                            config[key] = val
    return config


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"processed_sessions": {}, "last_run": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def find_transcript_files():
    """Find all Claude Code transcript JSONL files."""
    projects_dir = Path.home() / ".claude" / "projects"
    transcripts = []

    if not projects_dir.exists():
        return transcripts

    for jsonl in projects_dir.rglob("*.jsonl"):
        stat = jsonl.stat()
        transcripts.append({
            "path": str(jsonl),
            "modified": stat.st_mtime,
            "size": stat.st_size,
        })

    transcripts.sort(key=lambda x: x["modified"], reverse=True)
    return transcripts


def parse_transcript(path):
    """Parse a Claude Code transcript JSONL into structured messages."""
    messages = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg = extract_message(entry)
                if msg:
                    messages.append(msg)
    except (OSError, PermissionError):
        return []

    return messages


def extract_message(entry):
    """Extract relevant info from a transcript JSONL entry."""
    msg_data = entry.get("message", entry)
    role = msg_data.get("role", "")
    content = msg_data.get("content", "")
    timestamp = entry.get("timestamp", "")

    if isinstance(content, str) and content.strip():
        return {
            "role": role,
            "text": content.strip(),
            "timestamp": timestamp,
            "tool_uses": [],
            "files_changed": [],
        }

    if isinstance(content, list):
        texts = []
        tool_uses = []
        files_changed = []

        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "")
                    tool_input = block.get("input", {})
                    tool_uses.append(tool_name)

                    if tool_name in ("Write", "Edit", "MultiEdit"):
                        fp = tool_input.get("file_path", "")
                        if fp:
                            files_changed.append(fp)
                elif block.get("type") == "tool_result":
                    pass

        combined = "\n".join(t for t in texts if t.strip())
        if combined or tool_uses:
            return {
                "role": role,
                "text": combined,
                "timestamp": timestamp,
                "tool_uses": tool_uses,
                "files_changed": files_changed,
            }

    return None


TAG_RE = re.compile(r"<[^>]+>")
HEADER_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)

NOISE_PATTERNS = [
    "Caveat: The messages below were generated",
    "DO NOT respond to these messages",
    "/exit",
    "Bye!",
    "Claude Code diagnostics",
    "system-reminder",
    "local-command-stdout",
    "local-command-caveat",
    "command-name",
    "command-message",
    "command-args",
]


def sanitize_text(text):
    """Strip XML/system tags and neutralize markdown headers in embedded text."""
    text = TAG_RE.sub("", text)
    text = HEADER_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_noise(text):
    """Check if text is a system/command noise message."""
    stripped = text.strip()
    if len(stripped) < 5:
        return True
    for pattern in NOISE_PATTERNS:
        if pattern in stripped:
            return True
    return False


def compute_file_hash(path):
    """Hash file content to detect changes since last run."""
    h = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except (OSError, PermissionError):
        return ""
    return h.hexdigest()


def format_memory_entry(messages, session_id, project_name):
    """Format a list of messages into a markdown memory entry."""
    if not messages:
        return ""

    ts = messages[0].get("timestamp", "")
    if ts:
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    else:
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [f"## {date_str} — {project_name}"]
    lines.append(f"Session: `{session_id[:12]}`\n")

    all_files = []
    all_tools = []
    user_messages = []
    assistant_summaries = []

    for msg in messages:
        all_files.extend(msg.get("files_changed", []))
        all_tools.extend(msg.get("tool_uses", []))

        text = msg.get("text", "")
        if not text:
            continue

        if msg.get("role") == "user":
            clean = sanitize_text(text)
            if not clean or is_noise(clean):
                continue
            truncated = clean[:300] + "..." if len(clean) > 300 else clean
            user_messages.append(truncated)
        elif msg.get("role") == "assistant":
            clean = sanitize_text(text)
            if not clean or is_noise(clean):
                continue
            truncated = clean[:500] + "..." if len(clean) > 500 else clean
            assistant_summaries.append(truncated)

    if user_messages:
        lines.append("### User requests")
        for um in user_messages[:10]:
            lines.append(f"- {um}")
        lines.append("")

    if assistant_summaries:
        lines.append("### Key responses")
        for asum in assistant_summaries[:5]:
            lines.append(f"- {asum}")
        lines.append("")

    unique_files = list(dict.fromkeys(all_files))
    if unique_files:
        lines.append("### Files changed")
        for fp in unique_files[:20]:
            lines.append(f"- `{fp}`")
        lines.append("")

    unique_tools = list(dict.fromkeys(all_tools))
    if unique_tools:
        tool_counts = {}
        for t in all_tools:
            tool_counts[t] = tool_counts.get(t, 0) + 1
        tool_summary = ", ".join(f"{t}({c})" for t, c in sorted(tool_counts.items(), key=lambda x: -x[1])[:8])
        lines.append(f"### Tools used: {tool_summary}")
        lines.append("")

    lines.append("---\n")
    return "\n".join(lines)


def extract_project_name(transcript_path):
    """Derive project name from transcript path."""
    parts = Path(transcript_path).parts
    for i, part in enumerate(parts):
        if part == "projects" and i + 1 < len(parts):
            raw = parts[i + 1]
            # Claude stores as -Users-name-path-to-project
            if raw.startswith("-"):
                segments = raw.strip("-").split("-")
                if len(segments) >= 3:
                    return segments[-1]
                return raw
            return raw
    return "unknown-project"


def update_long_memory(new_entries, max_entries):
    """Append new entries to long-memory.md, respecting max entry count."""
    LONG_MEMORY.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if LONG_MEMORY.exists():
        existing = LONG_MEMORY.read_text()

    header = "# Long-Term Memory\n\n> Auto-generated by claude-custom-memory daemon. Do not edit manually.\n> Load with: `/custom-memory load long`\n\n"

    existing_entries = existing.split("\n## ")[1:] if "\n## " in existing else []
    new_entry_blocks = new_entries.split("\n## ")[1:] if "\n## " in new_entries else []

    all_entries = new_entry_blocks + existing_entries
    all_entries = all_entries[:max_entries]

    body = "\n## ".join(all_entries)
    if body:
        body = "\n## " + body

    LONG_MEMORY.write_text(header + body)


def update_short_memory(transcripts, hours, state):
    """Rebuild short-memory.md from transcripts within the time window."""
    SHORT_MEMORY.parent.mkdir(parents=True, exist_ok=True)
    cutoff = time.time() - (hours * 3600)

    recent_transcripts = [t for t in transcripts if t["modified"] >= cutoff]

    entries = []
    for t in recent_transcripts:
        messages = parse_transcript(t["path"])
        if not messages:
            continue

        session_id = Path(t["path"]).stem
        project = extract_project_name(t["path"])
        entry = format_memory_entry(messages, session_id, project)
        if entry:
            entries.append(entry)

    header = (
        "# Short-Term Memory\n\n"
        f"> Rolling {hours}-hour window. Auto-refreshed by claude-custom-memory daemon.\n"
        "> Load with: `/custom-memory load short`\n\n"
    )

    SHORT_MEMORY.write_text(header + "\n".join(entries))


def run_daemon(config_path=None):
    """Main daemon entry point."""
    config = load_config(config_path)
    state = load_state()

    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_CACHE.mkdir(parents=True, exist_ok=True)

    transcripts = find_transcript_files()
    if not transcripts:
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return

    processed = state.get("processed_sessions", {})
    new_entries = []

    for t in transcripts:
        file_hash = compute_file_hash(t["path"])
        session_id = Path(t["path"]).stem

        if processed.get(session_id) == file_hash:
            continue

        messages = parse_transcript(t["path"])
        if not messages:
            continue

        project = extract_project_name(t["path"])
        entry = format_memory_entry(messages, session_id, project)
        if entry:
            new_entries.append(entry)

        processed[session_id] = file_hash

    if new_entries:
        combined = "\n".join(new_entries)
        update_long_memory(combined, config["long_memory_max_entries"])

    update_short_memory(transcripts, config["short_memory_hours"], state)

    # Prune old session hashes (keep last 200)
    if len(processed) > 200:
        sorted_sessions = sorted(processed.items(), key=lambda x: x[1])
        processed = dict(sorted_sessions[-200:])

    state["processed_sessions"] = processed
    state["last_run"] = datetime.now().isoformat()
    save_state(state)


def extract_important(transcript_path=None, n_messages=10):
    """
    Extract last N messages from current/latest session and append to important.md.
    Called by the /important skill via: python3 memory-daemon.py --important [--transcript PATH] [--n 10]
    """
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    if transcript_path and os.path.exists(transcript_path):
        path = transcript_path
    else:
        transcripts = find_transcript_files()
        if not transcripts:
            print("No transcripts found.")
            return
        path = transcripts[0]["path"]

    messages = parse_transcript(path)
    if not messages:
        print("No messages found in transcript.")
        return

    tail = messages[-n_messages:]
    session_id = Path(path).stem
    project = extract_project_name(path)

    entry = format_memory_entry(tail, session_id, project)
    if not entry:
        print("No meaningful content in last messages.")
        return

    # Tag as user-flagged
    entry = entry.replace("\n---\n", "\n**Flagged as important by user**\n\n---\n", 1)

    header = "# Important Memory\n\n> User-flagged important moments. Load with: `/custom-memory load important`\n\n"

    existing = ""
    if IMPORTANT_MEMORY.exists():
        existing = IMPORTANT_MEMORY.read_text()
        if existing.startswith("# Important Memory"):
            existing = existing[existing.index("\n\n", existing.index("\n\n") + 2) + 2:]

    IMPORTANT_MEMORY.write_text(header + entry + existing)
    print(f"Flagged last {len(tail)} messages as important from {project}.")


def status():
    """Print daemon status."""
    state = load_state()
    last = state.get("last_run", "never")
    sessions = len(state.get("processed_sessions", {}))

    long_size = LONG_MEMORY.stat().st_size if LONG_MEMORY.exists() else 0
    short_size = SHORT_MEMORY.stat().st_size if SHORT_MEMORY.exists() else 0
    imp_size = IMPORTANT_MEMORY.stat().st_size if IMPORTANT_MEMORY.exists() else 0

    print(f"Last run: {last}")
    print(f"Sessions tracked: {sessions}")
    print(f"Long memory:  {long_size:,} bytes")
    print(f"Short memory: {short_size:,} bytes")
    print(f"Important:    {imp_size:,} bytes")


def main():
    parser = argparse.ArgumentParser(description="Claude Custom Memory Daemon")
    parser.add_argument("--config", help="Path to memory.conf", default=None)
    parser.add_argument("--important", action="store_true", help="Flag last N messages as important")
    parser.add_argument("--transcript", help="Transcript path (for --important)", default=None)
    parser.add_argument("--n", type=int, default=10, help="Number of messages for --important")
    parser.add_argument("--status", action="store_true", help="Print daemon status")
    parser.add_argument("--run", action="store_true", help="Run the daemon (default if no flags)")

    args = parser.parse_args()

    if args.important:
        extract_important(args.transcript, args.n)
    elif args.status:
        status()
    else:
        config_path = args.config
        if not config_path:
            default_conf = Path(__file__).parent / "memory.conf"
            if default_conf.exists():
                config_path = str(default_conf)
            else:
                home_conf = Path.home() / ".claude" / "memory" / "memory.conf"
                if home_conf.exists():
                    config_path = str(home_conf)
        run_daemon(config_path)


if __name__ == "__main__":
    main()

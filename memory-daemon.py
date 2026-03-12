#!/usr/bin/env python3
"""
Claude Custom Memory Daemon
Extracts conversation context from Claude Code sessions and maintains
project-scoped and global memory files.

Project memory:  <project-dir>/<project-name>-memory/<project-name>-{long,short,important}-memory.md
Global memory:   ~/.claude/memory/{long,short,important}-memory.md

Run via cron or manually: python3 memory-daemon.py [--config path/to/memory.conf]

SPDX-License-Identifier: MIT
"""

import json
import os
import re
import sys
import time
import hashlib
import argparse
from datetime import datetime
from pathlib import Path

GLOBAL_MEMORY_DIR = Path.home() / ".claude" / "memory"
STATE_FILE = GLOBAL_MEMORY_DIR / ".daemon-state.json"

DEFAULT_CONFIG = {
    "interval_hours": 1,
    "short_memory_hours": 3,
    "long_memory_max_entries": 500,
    "summarize": False,
    "important_max_messages": 10,
}

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


def extract_project_info(transcript_path):
    """Derive project name and project directory from transcript path.

    Claude stores transcripts at:
      ~/.claude/projects/-Users-name-path-to-project/session.jsonl

    The folder name encodes the absolute path with dashes, but directory names
    with hyphens/underscores make naive decoding unreliable. Instead, we
    progressively reconstruct the path by testing which segments exist on disk.
    """
    parts = Path(transcript_path).parts
    for i, part in enumerate(parts):
        if part == "projects" and i + 1 < len(parts):
            raw = parts[i + 1]
            if raw.startswith("-"):
                segments = raw.lstrip("-").split("-")

                # Greedily reconstruct path by joining segments and checking existence
                resolved = Path("/")
                remaining = segments[:]

                while remaining:
                    found = False
                    # Try joining progressively more segments (longest match first)
                    for end in range(len(remaining), 0, -1):
                        # Try common separators: hyphen, underscore, and direct join
                        for sep in ["-", "_", ""]:
                            candidate = sep.join(remaining[:end])
                            test_path = resolved / candidate
                            if test_path.exists():
                                resolved = test_path
                                remaining = remaining[end:]
                                found = True
                                break
                        if found:
                            break

                    if not found:
                        # Can't resolve further — use what we have
                        break

                if resolved.exists() and resolved.is_dir() and str(resolved) != "/":
                    return resolved.name, str(resolved)

                # Fallback: last segment of raw encoding
                return segments[-1], None
            return raw, None
    return "unknown-project", None


def write_memory_file(filepath, header, new_entries, max_entries=None):
    """Write or append entries to a memory markdown file."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if filepath.exists():
        existing = filepath.read_text()

    existing_entries = existing.split("\n## ")[1:] if "\n## " in existing else []
    new_entry_blocks = new_entries.split("\n## ")[1:] if "\n## " in new_entries else []

    all_entries = new_entry_blocks + existing_entries
    if max_entries:
        all_entries = all_entries[:max_entries]

    body = "\n## ".join(all_entries)
    if body:
        body = "\n## " + body

    filepath.write_text(header + body)


def build_short_memory(transcripts, hours, project_name=None, project_dir=None):
    """Build short memory content from recent transcripts."""
    cutoff = time.time() - (hours * 3600)
    recent = [t for t in transcripts if t["modified"] >= cutoff]

    entries = []
    for t in recent:
        t_project, _ = extract_project_info(t["path"])

        # If project-scoped, only include matching transcripts
        if project_name and t_project != project_name:
            continue

        messages = parse_transcript(t["path"])
        if not messages:
            continue

        session_id = Path(t["path"]).stem
        entry = format_memory_entry(messages, session_id, t_project)
        if entry:
            entries.append(entry)

    return "\n".join(entries)


def ensure_gitignore(proj_dir, pattern):
    """Add pattern to .gitignore if the project has one and pattern is missing."""
    gitignore = proj_dir / ".gitignore"
    if not gitignore.exists():
        return
    try:
        content = gitignore.read_text()
        if pattern in content:
            return
        sep = "" if content.endswith("\n") else "\n"
        gitignore.write_text(content + sep + pattern + "\n")
    except (OSError, PermissionError):
        pass


def run_daemon(config_path=None):
    """Main daemon entry point. Writes both project-scoped and global memory."""
    config = load_config(config_path)
    state = load_state()

    GLOBAL_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    transcripts = find_transcript_files()
    if not transcripts:
        state["last_run"] = datetime.now().isoformat()
        save_state(state)
        return

    processed = state.get("processed_sessions", {})

    # Group transcripts by project
    project_entries = {}  # project_name -> {"dir": path, "entries": [], "transcripts": []}
    global_entries = []

    for t in transcripts:
        file_hash = compute_file_hash(t["path"])
        session_id = Path(t["path"]).stem
        project_name, project_dir = extract_project_info(t["path"])

        # Track all transcripts per project (for short memory rebuild)
        if project_name not in project_entries:
            project_entries[project_name] = {"dir": project_dir, "entries": [], "transcripts": []}
        project_entries[project_name]["transcripts"].append(t)

        if processed.get(session_id) == file_hash:
            continue

        messages = parse_transcript(t["path"])
        if not messages:
            continue

        entry = format_memory_entry(messages, session_id, project_name)
        if entry:
            project_entries[project_name]["entries"].append(entry)
            global_entries.append(entry)

        processed[session_id] = file_hash

    # --- Write project-scoped memory ---
    for proj_name, proj_data in project_entries.items():
        proj_dir = proj_data["dir"]
        if not proj_dir or not Path(proj_dir).exists():
            continue

        memory_dir = Path(proj_dir) / f"{proj_name}-memory"
        ensure_gitignore(Path(proj_dir), f"{proj_name}-memory/")

        try:
            # Long memory (project)
            if proj_data["entries"]:
                long_header = (
                    f"# {proj_name} — Long-Term Memory\n\n"
                    f"> Auto-generated by claude-custom-memory daemon. Do not edit manually.\n"
                    f"> Load with: `/custom-memory load long`\n\n"
                )
                long_file = memory_dir / f"{proj_name}-long-memory.md"
                write_memory_file(long_file, long_header, "\n".join(proj_data["entries"]), config["long_memory_max_entries"])

            # Short memory (project)
            short_content = build_short_memory(proj_data["transcripts"], config["short_memory_hours"])
            if short_content:
                short_header = (
                    f"# {proj_name} — Short-Term Memory\n\n"
                    f"> Rolling {config['short_memory_hours']}-hour window. Auto-refreshed by daemon.\n"
                    f"> Load with: `/custom-memory load short`\n\n"
                )
                short_file = memory_dir / f"{proj_name}-short-memory.md"
                short_file.parent.mkdir(parents=True, exist_ok=True)
                short_file.write_text(short_header + short_content)
        except PermissionError:
            # macOS TCC blocks cron from ~/Desktop, ~/Documents, ~/Downloads
            continue

    # --- Write global memory ---

    # Global long memory
    if global_entries:
        global_long_header = (
            "# Global Long-Term Memory\n\n"
            "> All projects, all sessions. Auto-generated by claude-custom-memory daemon.\n"
            "> Load with: `/custom-memory all load long`\n\n"
        )
        write_memory_file(
            GLOBAL_MEMORY_DIR / "long-memory.md",
            global_long_header,
            "\n".join(global_entries),
            config["long_memory_max_entries"],
        )

    # Global short memory
    global_short_content = build_short_memory(transcripts, config["short_memory_hours"])
    global_short_header = (
        "# Global Short-Term Memory\n\n"
        f"> Rolling {config['short_memory_hours']}-hour window, all projects.\n"
        "> Load with: `/custom-memory all load short`\n\n"
    )
    global_short_file = GLOBAL_MEMORY_DIR / "short-memory.md"
    global_short_file.write_text(global_short_header + global_short_content)

    # Prune old session hashes (keep last 200)
    if len(processed) > 200:
        sorted_sessions = sorted(processed.items(), key=lambda x: x[1])
        processed = dict(sorted_sessions[-200:])

    state["processed_sessions"] = processed
    state["last_run"] = datetime.now().isoformat()
    save_state(state)


def extract_important(transcript_path=None, n_messages=10, project_dir=None):
    """
    Extract last N messages and write to project-scoped important memory.
    Falls back to global if project dir can't be determined.
    """
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
    project_name, detected_dir = extract_project_info(path)

    entry = format_memory_entry(tail, session_id, project_name)
    if not entry:
        print("No meaningful content in last messages.")
        return

    entry = entry.replace("\n---\n", "\n**Flagged as important by user**\n\n---\n", 1)

    # Determine where to write
    target_dir = project_dir or detected_dir
    if target_dir and Path(target_dir).exists():
        memory_dir = Path(target_dir) / f"{project_name}-memory"
        important_file = memory_dir / f"{project_name}-important-memory.md"
        header = (
            f"# {project_name} — Important Memory\n\n"
            f"> User-flagged important moments.\n"
            f"> Load with: `/custom-memory load important`\n\n"
        )
    else:
        important_file = GLOBAL_MEMORY_DIR / "important-memory.md"
        header = (
            "# Important Memory\n\n"
            "> User-flagged important moments.\n"
            "> Load with: `/custom-memory all load important`\n\n"
        )

    important_file.parent.mkdir(parents=True, exist_ok=True)

    existing = ""
    if important_file.exists():
        existing = important_file.read_text()
        # Strip existing header
        marker = "\n\n---"
        first_entry = existing.find("\n## ")
        if first_entry > 0:
            existing = existing[first_entry:]
        else:
            existing = ""

    important_file.write_text(header + entry + existing)
    print(f"Flagged last {len(tail)} messages as important for {project_name}.")
    print(f"Saved to: {important_file}")


def status():
    """Print daemon status."""
    state = load_state()
    last = state.get("last_run", "never")
    sessions = len(state.get("processed_sessions", {}))

    print(f"Last run:         {last}")
    print(f"Sessions tracked: {sessions}")
    print()

    # Global memory
    print("Global memory (~/.claude/memory/):")
    for name in ["long-memory.md", "short-memory.md", "important-memory.md"]:
        f = GLOBAL_MEMORY_DIR / name
        size = f.stat().st_size if f.exists() else 0
        print(f"  {name}: {size:,} bytes")

    # Find project memories
    print()
    print("Project memories:")
    projects_dir = Path.home() / ".claude" / "projects"
    if projects_dir.exists():
        seen = set()
        for jsonl in projects_dir.rglob("*.jsonl"):
            proj_name, proj_dir = extract_project_info(str(jsonl))
            if proj_name in seen or not proj_dir:
                continue
            seen.add(proj_name)

            memory_dir = Path(proj_dir) / f"{proj_name}-memory"
            if memory_dir.exists():
                files = list(memory_dir.glob("*.md"))
                total = sum(f.stat().st_size for f in files)
                print(f"  {proj_name}: {len(files)} files, {total:,} bytes ({memory_dir})")


def main():
    parser = argparse.ArgumentParser(description="Claude Custom Memory Daemon")
    parser.add_argument("--config", help="Path to memory.conf", default=None)
    parser.add_argument("--important", action="store_true", help="Flag last N messages as important")
    parser.add_argument("--transcript", help="Transcript path (for --important)", default=None)
    parser.add_argument("--project-dir", help="Project directory (for --important)", default=None)
    parser.add_argument("--n", type=int, default=10, help="Number of messages for --important")
    parser.add_argument("--status", action="store_true", help="Print daemon status")
    parser.add_argument("--run", action="store_true", help="Run the daemon (default if no flags)")

    args = parser.parse_args()

    if args.important:
        extract_important(args.transcript, args.n, args.project_dir)
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

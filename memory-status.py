#!/usr/bin/env python3
"""
Claude Custom Memory Status Dashboard
Lists all projects, their memory files, sizes, last updated times, and recent entries.

Usage:
  python3 memory-status.py              # summary table
  python3 memory-status.py --detail     # include last entry preview per project
  python3 memory-status.py --project X  # deep dive into one project
  python3 memory-status.py --global     # show global memory info
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path


GLOBAL_MEMORY_DIR = Path.home() / ".claude" / "memory"
STATE_FILE = GLOBAL_MEMORY_DIR / ".daemon-state.json"

MEMORY_TYPES = ["long", "short", "important"]


def fmt_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f}MB"


def fmt_age(mtime):
    delta = datetime.now().timestamp() - mtime
    if delta < 60:
        return "just now"
    elif delta < 3600:
        return f"{int(delta / 60)}m ago"
    elif delta < 86400:
        return f"{int(delta / 3600)}h ago"
    else:
        return f"{int(delta / 86400)}d ago"


def fmt_date(mtime):
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")


def count_entries(filepath):
    """Count ## headers (each is one memory entry)."""
    try:
        text = filepath.read_text()
        return text.count("\n## ")
    except (OSError, PermissionError):
        return 0


def last_entry_preview(filepath, max_lines=6):
    """Extract the first few lines of the most recent entry."""
    try:
        text = filepath.read_text()
    except (OSError, PermissionError):
        return "(unreadable)"

    parts = text.split("\n## ")
    if len(parts) < 2:
        return "(empty)"

    # First non-header entry (most recent is typically index 1)
    entry = parts[1]
    lines = entry.strip().split("\n")[:max_lines]
    return "\n".join(f"    {line}" for line in lines)


def find_project_memories():
    """Scan for all project memory directories."""
    projects = []

    # Scan Claude's projects dir to find all known project paths
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        return projects

    seen_dirs = set()

    for project_dir in claude_projects.iterdir():
        if not project_dir.is_dir() or not project_dir.name.startswith("-"):
            continue

        # Decode project path from Claude's encoding
        segments = project_dir.name.lstrip("-").split("-")
        resolved = Path("/")
        remaining = segments[:]

        while remaining:
            found = False
            for end in range(len(remaining), 0, -1):
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
                break

        if not resolved.is_dir() or str(resolved) == "/":
            continue

        proj_name = resolved.name
        proj_dir = str(resolved)

        if proj_dir in seen_dirs:
            continue
        seen_dirs.add(proj_dir)

        memory_dir = resolved / f"{proj_name}-memory"
        if not memory_dir.exists():
            continue

        info = {
            "name": proj_name,
            "dir": proj_dir,
            "memory_dir": str(memory_dir),
            "files": {},
            "total_size": 0,
            "total_entries": 0,
            "last_updated": 0,
        }

        for mem_type in MEMORY_TYPES:
            f = memory_dir / f"{proj_name}-{mem_type}-memory.md"
            if f.exists():
                stat = f.stat()
                entries = count_entries(f)
                info["files"][mem_type] = {
                    "path": str(f),
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "entries": entries,
                }
                info["total_size"] += stat.st_size
                info["total_entries"] += entries
                if stat.st_mtime > info["last_updated"]:
                    info["last_updated"] = stat.st_mtime

        if info["files"]:
            projects.append(info)

    projects.sort(key=lambda x: x["last_updated"], reverse=True)
    return projects


def get_global_info():
    info = {"files": {}, "total_size": 0, "total_entries": 0, "last_updated": 0}
    for mem_type in MEMORY_TYPES:
        f = GLOBAL_MEMORY_DIR / f"{mem_type}-memory.md"
        if f.exists():
            stat = f.stat()
            entries = count_entries(f)
            info["files"][mem_type] = {
                "path": str(f),
                "size": stat.st_size,
                "mtime": stat.st_mtime,
                "entries": entries,
            }
            info["total_size"] += stat.st_size
            info["total_entries"] += entries
            if stat.st_mtime > info["last_updated"]:
                info["last_updated"] = stat.st_mtime
    return info


def get_daemon_status():
    if not STATE_FILE.exists():
        return None
    import json
    with open(STATE_FILE) as f:
        return json.load(f)


def print_summary(projects, show_detail=False):
    state = get_daemon_status()
    global_info = get_global_info()

    # Header
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           Claude Custom Memory — Status Dashboard          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    # Daemon status
    if state:
        last_run = state.get("last_run", "never")
        sessions = len(state.get("processed_sessions", {}))
        print(f"  Daemon last run:  {last_run}")
        print(f"  Sessions tracked: {sessions}")
    else:
        print("  Daemon: no state file found (has it ever run?)")
    print()

    # Global memory
    print("  Global Memory (~/.claude/memory/)")
    print("  ─────────────────────────────────")
    for mem_type in MEMORY_TYPES:
        if mem_type in global_info["files"]:
            f = global_info["files"][mem_type]
            print(f"    {mem_type:10s}  {fmt_size(f['size']):>8s}  {f['entries']:>4d} entries  updated {fmt_age(f['mtime'])}")
        else:
            print(f"    {mem_type:10s}  {'—':>8s}")
    print(f"    {'total':10s}  {fmt_size(global_info['total_size']):>8s}  {global_info['total_entries']:>4d} entries")
    print()

    # Projects table
    total_disk = global_info["total_size"]
    print(f"  Project Memories ({len(projects)} projects)")
    print("  ─────────────────────────────────")
    print(f"  {'Project':<25s} {'Size':>8s} {'Entries':>8s} {'Long':>6s} {'Short':>6s} {'Imp':>6s} {'Updated':<12s}")
    print(f"  {'─' * 25} {'─' * 8} {'─' * 8} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 12}")

    for p in projects:
        total_disk += p["total_size"]
        long_e = p["files"].get("long", {}).get("entries", "—")
        short_e = p["files"].get("short", {}).get("entries", "—")
        imp_e = p["files"].get("important", {}).get("entries", "—")
        updated = fmt_age(p["last_updated"]) if p["last_updated"] else "never"

        name = p["name"][:25]
        print(f"  {name:<25s} {fmt_size(p['total_size']):>8s} {p['total_entries']:>8d} {str(long_e):>6s} {str(short_e):>6s} {str(imp_e):>6s} {updated:<12s}")

        if show_detail and "long" in p["files"]:
            preview = last_entry_preview(Path(p["files"]["long"]["path"]))
            print(f"    Latest entry:")
            print(preview)
            print()

    print()
    print(f"  Total disk usage: {fmt_size(total_disk)} across {len(projects)} projects + global")
    print()


def print_project_detail(projects, project_name):
    matches = [p for p in projects if p["name"].lower() == project_name.lower()]
    if not matches:
        # Fuzzy match
        matches = [p for p in projects if project_name.lower() in p["name"].lower()]

    if not matches:
        print(f"No project found matching '{project_name}'")
        print(f"Available: {', '.join(p['name'] for p in projects)}")
        return

    p = matches[0]
    print(f"  Project: {p['name']}")
    print(f"  Directory: {p['dir']}")
    print(f"  Memory dir: {p['memory_dir']}")
    print(f"  Total size: {fmt_size(p['total_size'])}")
    print(f"  Total entries: {p['total_entries']}")
    print()

    for mem_type in MEMORY_TYPES:
        if mem_type not in p["files"]:
            print(f"  {mem_type}: (none)")
            continue

        f = p["files"][mem_type]
        print(f"  {mem_type}:")
        print(f"    Path:    {f['path']}")
        print(f"    Size:    {fmt_size(f['size'])}")
        print(f"    Entries: {f['entries']}")
        print(f"    Updated: {fmt_date(f['mtime'])} ({fmt_age(f['mtime'])})")

        preview = last_entry_preview(Path(f["path"]))
        print(f"    Latest:")
        print(preview)
        print()


def print_global_detail():
    info = get_global_info()
    print(f"  Global Memory")
    print(f"  Directory: {GLOBAL_MEMORY_DIR}")
    print(f"  Total size: {fmt_size(info['total_size'])}")
    print(f"  Total entries: {info['total_entries']}")
    print()

    for mem_type in MEMORY_TYPES:
        if mem_type not in info["files"]:
            print(f"  {mem_type}: (none)")
            continue

        f = info["files"][mem_type]
        print(f"  {mem_type}:")
        print(f"    Path:    {f['path']}")
        print(f"    Size:    {fmt_size(f['size'])}")
        print(f"    Entries: {f['entries']}")
        print(f"    Updated: {fmt_date(f['mtime'])} ({fmt_age(f['mtime'])})")

        preview = last_entry_preview(Path(f["path"]))
        print(f"    Latest:")
        print(preview)
        print()


def main():
    parser = argparse.ArgumentParser(description="Claude Custom Memory Status Dashboard")
    parser.add_argument("--detail", action="store_true", help="Show last entry preview for each project")
    parser.add_argument("--project", "-p", help="Deep dive into a specific project")
    parser.add_argument("--global", dest="show_global", action="store_true", help="Show global memory detail")
    args = parser.parse_args()

    projects = find_project_memories()

    if args.project:
        print_project_detail(projects, args.project)
    elif args.show_global:
        print_global_detail()
    else:
        print_summary(projects, show_detail=args.detail)


if __name__ == "__main__":
    main()

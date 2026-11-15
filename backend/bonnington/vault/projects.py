"""Which coding projects are in progress, read from Claude Code's local session logs. Read-only.

Nothing is sent anywhere and nothing under ~/.claude or the project folders is ever written.
The user's own word on a project ("on hold", "done") lives in the vault under Projects/.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ACTIVE_DAYS = 7
STALLED_DAYS = 30
HEAD_BYTES = 64 * 1024
TAIL_BYTES = 256 * 1024
USER_STATES = ("on hold", "done")


@dataclass
class ProjectStatus:
    name: str            # folder relative to the projects root, e.g. "tensor/campusai"
    path: Path
    last_active: datetime
    days_idle: int
    state: str           # active | stalled | cold | on hold | done
    area: str            # Academic | Personal
    title: str = ""      # what the latest session was about
    branch: str = ""
    note: str = ""


def _read_chunks(p: Path) -> list[str]:
    """First and last part of a session log: enough for the folder, title and branch without reading 18 MB."""
    size = p.stat().st_size
    with p.open("rb") as f:
        head = f.read(HEAD_BYTES)
        tail = b""
        if size > HEAD_BYTES:
            f.seek(max(HEAD_BYTES, size - TAIL_BYTES))
            tail = f.read()
    return (head + b"\n" + tail).decode("utf-8", errors="replace").splitlines()


def _session_info(p: Path) -> tuple[str, str, str]:
    cwd = title = branch = ""
    for line in _read_chunks(p):
        if not line.startswith("{"):
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        cwd = cwd or row.get("cwd") or ""
        branch = row.get("gitBranch") or branch
        title = row.get("customTitle") or row.get("aiTitle") or title
    return cwd, title, branch


def _project_root(cwd: Path) -> Path:
    """A session inside <project>/.claude/worktrees/<x> belongs to <project>."""
    parts = cwd.parts
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "worktrees":
            return Path(*parts[:i])
    return cwd


def scan_projects(claude_dir: Path, projects_root: Path, academic_folders: list[str],
                  now: datetime) -> list[ProjectStatus]:
    claude_dir, projects_root = Path(claude_dir), Path(projects_root).resolve()
    best: dict[Path, tuple[float, str, str]] = {}
    if not claude_dir.is_dir():
        return []
    for log in claude_dir.glob("*/*.jsonl"):
        try:
            mtime = log.stat().st_mtime
            cwd, title, branch = _session_info(log)
        except OSError:
            continue
        if not cwd:
            continue
        folder = _project_root(Path(cwd)).resolve()
        if projects_root not in folder.parents or not folder.is_dir():
            continue
        if folder not in best or mtime > best[folder][0]:
            best[folder] = (mtime, title or (best.get(folder) or (0, "", ""))[1], branch)
    out = []
    academic = {a.lower() for a in academic_folders}
    for folder, (mtime, title, branch) in best.items():
        rel = folder.relative_to(projects_root)
        last = datetime.fromtimestamp(mtime)
        idle = max(0, (now - last).days)
        state = "active" if idle <= ACTIVE_DAYS else "stalled" if idle <= STALLED_DAYS else "cold"
        area = "Academic" if academic & {p.lower() for p in rel.parts} else "Personal"
        out.append(ProjectStatus(rel.as_posix(), folder, last, idle, state, area, title, branch))
    return sorted(out, key=lambda p: p.days_idle)


def _note_path(vault_root: Path, name: str) -> Path:
    return Path(vault_root) / "Projects" / (re.sub(r'[\\/:*?"<>|]', "__", name) + ".md")


def set_project_status(vault_root: Path, name: str, status: str, note: str = "") -> None:
    """Record the user's word on a project: 'on hold', 'done', or 'active' to clear it."""
    p = _note_path(vault_root, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    kept = []
    if p.exists():
        kept = [l for l in p.read_text(encoding="utf-8").splitlines()
                if not re.match(r"(status|note|project):", l)]
    header = [f"project: {name}"]
    if status in USER_STATES:
        header.append(f"status: {status}")
        if note:
            header.append(f"note: {note}")
    p.write_text("\n".join(header + kept).rstrip("\n") + "\n", encoding="utf-8")


def read_project_notes(vault_root: Path) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    folder = Path(vault_root) / "Projects"
    if not folder.is_dir():
        return out
    for p in folder.glob("*.md"):
        fields = dict(m.groups() for l in p.read_text(encoding="utf-8").splitlines()
                      if (m := re.match(r"(status|note|project):\s*(.*)", l)))
        if fields.get("project") and fields.get("status") in USER_STATES:
            out[fields["project"]] = (fields["status"], fields.get("note", ""))
    return out


def project_statuses(vault_root: Path, claude_dir: Path, projects_root: Path,
                     academic_folders: list[str], now: datetime) -> list[ProjectStatus]:
    notes = read_project_notes(vault_root)
    projects = scan_projects(claude_dir, projects_root, academic_folders, now)
    for p in projects:
        if p.name in notes:
            p.state, p.note = notes[p.name]
    return projects

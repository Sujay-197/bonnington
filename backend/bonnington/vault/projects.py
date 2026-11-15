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


_SECRET_WORDS = re.compile(r"api[-_ ]?key|secret|password|passwd|token|bearer|authorization|private key",
                           re.IGNORECASE)
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_\-.]{24,}")
_HIDDEN = "(a request containing a key or password, hidden)"
_NOT_TYPED = ("<", "[Request interrupted", "Caveat:")
MAX_REQUEST_CHARS = 160


def _clean_request(text: str) -> str | None:
    """A past request, safe to show and say: no injected text, no secrets, not too long."""
    text = " ".join(text.split())
    if not text or text.startswith(_NOT_TYPED) or "<system-reminder>" in text or "<command-name>" in text:
        return None
    if _SECRET_WORDS.search(text) or any(re.search(r"\d", t) and re.search(r"[A-Za-z]", t)
                                         for t in _LONG_TOKEN.findall(text)):
        return _HIDDEN
    return text if len(text) <= MAX_REQUEST_CHARS else text[:MAX_REQUEST_CHARS].rstrip() + "\u2026"


def _session_info(p: Path) -> tuple[str, str, str]:
    cwd, title, branch, _ = _parse_session(p)
    return cwd, title, branch


def _parse_session(p: Path) -> tuple[str, str, str, list[str]]:
    cwd = title = branch = ""
    prompts: list[str] = []
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
        if row.get("type") == "user" and (row.get("origin") or {}).get("kind", "human") == "human":
            content = (row.get("message") or {}).get("content")
            if isinstance(content, str):
                cleaned = _clean_request(content)
                if cleaned and (not prompts or prompts[-1] != cleaned):
                    prompts.append(cleaned)
    return cwd, title, branch, prompts


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


@dataclass
class ProjectDetail:
    name: str
    sessions: list[tuple[str, int]]   # (title, days ago), newest first
    requests: list[str]               # what the user last asked for there, newest first


def project_detail(claude_dir: Path, projects_root: Path, name: str, now: datetime,
                   max_sessions: int = 3, max_requests: int = 5) -> ProjectDetail | None:
    """Recent sessions and requests for one project, from the local session logs."""
    claude_dir, projects_root = Path(claude_dir), Path(projects_root).resolve()
    found: list[tuple[float, str, list[str]]] = []
    if not claude_dir.is_dir():
        return None
    for log in claude_dir.glob("*/*.jsonl"):
        try:
            mtime = log.stat().st_mtime
            cwd, title, _branch, prompts = _parse_session(log)
        except OSError:
            continue
        if not cwd:
            continue
        folder = _project_root(Path(cwd)).resolve()
        if projects_root in folder.parents and folder.relative_to(projects_root).as_posix() == name:
            found.append((mtime, title, prompts))
    if not found:
        return None
    found.sort(key=lambda f: f[0], reverse=True)
    sessions = [(title or "untitled session", max(0, (now - datetime.fromtimestamp(m)).days))
                for m, title, _ in found[:max_sessions]]
    requests: list[str] = []
    for _, _, prompts in found:
        for r in reversed(prompts):
            if len(requests) < max_requests and (not requests or requests[-1] != r):
                requests.append(r)
    return ProjectDetail(name, sessions, requests)

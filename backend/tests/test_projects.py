import json
import os
from datetime import datetime, timedelta

from bonnington.vault.projects import project_statuses, read_project_notes, scan_projects, set_project_status

NOW = datetime(2026, 11, 15, 12, 0)


def _session(claude_dir, folder, cwd, days_ago, title=None, branch="main", name="s1"):
    d = claude_dir / folder
    d.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "user", "cwd": str(cwd), "gitBranch": branch, "timestamp": "2026-11-01T00:00:00Z"}]
    if title:
        lines.append({"type": "custom-title", "customTitle": title, "sessionId": name})
    p = d / f"{name}.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    ts = (NOW - timedelta(days=days_ago)).timestamp()
    os.utime(p, (ts, ts))
    return p


def _world(tmp_path):
    root = tmp_path / "work"
    for sub in ("medrag", "clg/funda", "tensor/campusai", "truco"):
        (root / sub).mkdir(parents=True)
    return tmp_path / "claude", root


def test_scan_reads_folder_title_branch_and_age(tmp_path):
    claude, root = _world(tmp_path)
    _session(claude, "a", root / "medrag", 6, title="Stitch MCP integration", branch="feat/step0")
    (p,) = scan_projects(claude, root, ["clg"], NOW)
    assert p.name == "medrag" and p.title == "Stitch MCP integration" and p.branch == "feat/step0"
    assert p.days_idle == 6 and p.state == "active" and p.area == "Personal"


def test_states_by_idle_time(tmp_path):
    claude, root = _world(tmp_path)
    _session(claude, "a", root / "medrag", 7)
    _session(claude, "b", root / "truco", 8)
    _session(claude, "c", root / "tensor" / "campusai", 31)
    states = {p.name: p.state for p in scan_projects(claude, root, ["clg"], NOW)}
    assert states == {"medrag": "active", "truco": "stalled", "tensor/campusai": "cold"}


def test_academic_folder_sets_area(tmp_path):
    claude, root = _world(tmp_path)
    _session(claude, "a", root / "clg" / "funda", 2)
    assert scan_projects(claude, root, ["clg"], NOW)[0].area == "Academic"


def test_newest_session_wins_and_sessions_group_by_folder(tmp_path):
    claude, root = _world(tmp_path)
    _session(claude, "a", root / "medrag", 40, title="Old work", name="old")
    _session(claude, "a", root / "medrag", 3, title="New work", name="new")
    (p,) = scan_projects(claude, root, ["clg"], NOW)
    assert p.title == "New work" and p.days_idle == 3


def test_worktrees_count_towards_their_project(tmp_path):
    claude, root = _world(tmp_path)
    wt = root / "tensor" / "campusai" / ".claude" / "worktrees" / "ui-home"
    wt.mkdir(parents=True)
    _session(claude, "a", root / "tensor" / "campusai", 20)
    _session(claude, "b", wt, 1, title="UI home")
    (p,) = scan_projects(claude, root, ["clg"], NOW)
    assert p.name == "tensor/campusai" and p.days_idle == 1


def test_folders_outside_the_projects_root_or_deleted_are_skipped(tmp_path):
    claude, root = _world(tmp_path)
    _session(claude, "a", tmp_path / "Temp" / "scratch", 1)
    _session(claude, "b", root / "deleted-project", 1)
    assert scan_projects(claude, root, ["clg"], NOW) == []


def test_garbage_lines_and_missing_dir_do_not_crash(tmp_path):
    claude, root = _world(tmp_path)
    assert scan_projects(claude, root, ["clg"], NOW) == []
    p = _session(claude, "a", root / "medrag", 1)
    p.write_text("not json\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    ts = (NOW - timedelta(days=1)).timestamp()
    os.utime(p, (ts, ts))
    assert len(scan_projects(claude, root, ["clg"], NOW)) == 1


def test_user_can_put_a_project_on_hold(tmp_path):
    claude, root = _world(tmp_path)
    vault = tmp_path / "vault"
    _session(claude, "a", root / "tensor" / "campusai", 31)
    set_project_status(vault, "tensor/campusai", "on hold", "until exams end")
    assert read_project_notes(vault) == {"tensor/campusai": ("on hold", "until exams end")}
    (p,) = project_statuses(vault, claude, root, ["clg"], NOW)
    assert p.state == "on hold" and p.note == "until exams end"
    text = (vault / "Projects" / "tensor__campusai.md").read_text(encoding="utf-8")
    assert "status: on hold" in text


def test_setting_status_active_clears_the_hold(tmp_path):
    claude, root = _world(tmp_path)
    vault = tmp_path / "vault"
    _session(claude, "a", root / "medrag", 2)
    set_project_status(vault, "medrag", "done")
    set_project_status(vault, "medrag", "active")
    assert project_statuses(vault, claude, root, ["clg"], NOW)[0].state == "active"

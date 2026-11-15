import subprocess
from pathlib import Path

from bonnington.ui_process import UIProcess


class FakeProc:
    def __init__(self, dies_on_terminate=True):
        self.alive = True
        self.dies = dies_on_terminate
        self.terminated = self.killed = False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.terminated = True
        if self.dies:
            self.alive = False

    def wait(self, timeout=None):
        if self.alive:
            raise subprocess.TimeoutExpired("ui", timeout)
        return 0

    def kill(self):
        self.killed = True
        self.alive = False


class FakePopen:
    def __init__(self, **kw):
        self.spawned = []
        self.kw = kw

    def __call__(self, args, **kw):
        p = FakeProc(**self.kw)
        self.spawned.append((args, p))
        return p


def test_show_twice_spawns_once():
    popen = FakePopen()
    ui = UIProcess(Path("ui.exe"), popen=popen)
    ui.show()
    ui.show()
    assert len(popen.spawned) == 1 and ui.is_running


def test_hide_terminates():
    popen = FakePopen()
    ui = UIProcess(Path("ui.exe"), popen=popen)
    ui.show()
    ui.hide()
    p = popen.spawned[0][1]
    assert p.terminated and not p.killed and not ui.is_running


def test_hide_kills_if_terminate_ignored():
    popen = FakePopen(dies_on_terminate=False)
    ui = UIProcess(Path("ui.exe"), popen=popen, wait_s=0.01)
    ui.show()
    ui.hide()
    assert popen.spawned[0][1].killed and not ui.is_running


def test_hide_when_not_running_is_noop():
    UIProcess(Path("ui.exe"), popen=FakePopen()).hide()


def test_show_respawns_after_window_closed_by_user():
    popen = FakePopen()
    ui = UIProcess(Path("ui.exe"), popen=popen)
    ui.show()
    popen.spawned[0][1].alive = False
    ui.show()
    assert len(popen.spawned) == 2

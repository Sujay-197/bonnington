"""Launches the Tauri window when Bonnington wakes and kills it when he sleeps (it holds no memory while dormant)."""

from __future__ import annotations

import subprocess
from pathlib import Path


class UIProcess:
    def __init__(self, exe: Path, popen=subprocess.Popen, wait_s: float = 3.0) -> None:
        self.exe = Path(exe)
        self._popen = popen
        self.wait_s = wait_s
        self._proc = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def show(self) -> None:
        if self.is_running:
            return
        self._proc = self._popen([str(self.exe)], cwd=str(self.exe.parent))

    def hide(self) -> None:
        p, self._proc = self._proc, None
        if p is None or p.poll() is not None:
            return
        p.terminate()
        try:
            p.wait(timeout=self.wait_s)
        except subprocess.TimeoutExpired:
            p.kill()

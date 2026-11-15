"""Windows probes: is a game/full-screen app in front, and is another app using the mic (a call)."""

from __future__ import annotations

from collections.abc import Iterable

_CONSENT = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

# SHQueryUserNotificationState: 2 = busy (full-screen app), 3 = D3D full-screen game, 4 = presentation.
_BUSY_STATES = {2, 3, 4}


def _busy_state(state: int) -> bool:
    return state in _BUSY_STATES


def is_fullscreen_app() -> bool:
    import ctypes
    state = ctypes.c_int(0)
    if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return _busy_state(state.value)


class _WinReg:
    """Yields (subkey path, LastUsedTimeStart, LastUsedTimeStop) for every app under the mic consent store."""

    def entries(self):
        import winreg

        def walk(path):
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                return
            with key:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(key, i)
                    except OSError:
                        break
                    i += 1
                    sub = path + "\\" + name
                    if name == "NonPackaged":
                        yield from walk(sub)
                        continue
                    try:
                        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
                            start = winreg.QueryValueEx(k, "LastUsedTimeStart")[0]
                            stop = winreg.QueryValueEx(k, "LastUsedTimeStop")[0]
                    except OSError:
                        continue
                    yield sub[len(_CONSENT) + 1:].replace("\\", "/"), start, stop

        return list(walk(_CONSENT))


def mic_in_use_by_other(own_exe: str | Iterable[str], reg=None) -> bool:
    own = [own_exe] if isinstance(own_exe, str) else list(own_exe)
    own = [o.lower() for o in own]
    for path, start, stop in (reg or _WinReg()).entries():
        if start and stop == 0 and not any(o in path.lower() for o in own):
            return True
    return False

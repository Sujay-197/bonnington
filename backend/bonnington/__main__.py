"""Entry point: `python -m bonnington` runs the tray + backend. `--register-startup` adds a login shortcut."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # das_v0/
UI_EXE = ROOT / "ui" / "src-tauri" / "target" / "release" / "bonnington-ui.exe"


def register_startup() -> Path:
    startup = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    target = startup / "Bonnington.cmd"
    target.write_text(f'@start "" /D "{ROOT}" "{pythonw}" -m bonnington\r\n', encoding="utf-8")
    return target


async def _amain(state: dict) -> None:
    from .audio.player import AudioPlayer
    from .audio.source import MicSource
    from .brain.llm import Brain
    from .bridge import UIBridge
    from .config import load_settings, save_settings
    from .events import AmplitudeEvent
    from .hotkey import HotkeyListener
    from .lifecycle import LifecycleController
    from .orchestrator import Deps, Orchestrator
    from .store import GrudgeStore
    from .stt import SherpaSTT
    from .tts import TTSEngine, Utterance
    from .ui_process import UIProcess
    from .vad import TurnDetector
    from .wake import WakeDetector

    settings = load_settings(ROOT / "data" / "settings.json")
    bridge = UIBridge(settings.ws_port)
    player = AudioPlayer(lambda v: bridge.broadcast(AmplitudeEvent(v)))

    async def play_file(path: str) -> None:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=False)
        await player.play(Utterance(data, sr, ""))

    mic = MicSource()
    deps = Deps(source=mic, wake=WakeDetector(settings.wake_models, settings.wake_threshold),
                turn=TurnDetector(), stt=SherpaSTT(settings), brain=Brain(settings.llm_model),
                tts=TTSEngine(settings), player=player, bridge=bridge,
                store=GrudgeStore(ROOT / "data" / "bonnington.db"), settings=settings,
                play_file=play_file)
    orch = Orchestrator(deps)
    controller = LifecycleController(orch, mic, UIProcess(UI_EXE),
                                     idle_unload_s=settings.idle_unload_seconds)
    loop = asyncio.get_running_loop()
    hotkey = HotkeyListener(settings.hotkey, lambda: loop.call_soon_threadsafe(orch.trigger, "hotkey"))

    def set_headphones(on: bool) -> None:
        settings.headphones_mode = on
        save_settings(settings, ROOT / "data" / "settings.json")

    state.update(controller=controller, settings=settings, set_headphones=set_headphones, loop=loop)
    state["ready"].set()
    await bridge.start()
    hotkey.start()
    try:
        await asyncio.gather(orch.run(), controller.run())
    finally:
        hotkey.stop()
        await bridge.stop()


def main() -> None:
    ap = argparse.ArgumentParser(prog="bonnington")
    ap.add_argument("--register-startup", action="store_true")
    args = ap.parse_args()
    if args.register_startup:
        print(f"registered: {register_startup()}")
        return

    os.chdir(ROOT)
    (ROOT / "data").mkdir(exist_ok=True)
    logging.basicConfig(filename=ROOT / "data" / "bonnington.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    state: dict = {"ready": threading.Event()}
    worker = threading.Thread(target=lambda: asyncio.run(_amain(state)), daemon=True)
    worker.start()
    state["ready"].wait()

    from .tray import Tray
    controller, settings = state["controller"], state["settings"]
    tray = Tray(get_dnd=lambda: controller._dnd, set_dnd=controller.set_dnd,
                get_headphones=lambda: settings.headphones_mode,
                set_headphones=state["set_headphones"], on_quit=lambda: None)
    controller.on_level_change = lambda lvl: tray.set_level(lvl.value)
    tray.run()  # returns on Quit; the daemon worker dies with the process


if __name__ == "__main__":
    main()

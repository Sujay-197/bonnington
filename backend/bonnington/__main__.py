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
    from .presenter import Presenter
    from .store import GrudgeStore
    from .stt import build_stt
    from .tts import TTSEngine, Utterance
    from .ui_process import UIProcess
    from .vad import TurnDetector
    from .vault.tools import build_tracker
    from .wake import SttWake

    settings = load_settings(ROOT / "data" / "settings.json")
    bridge = UIBridge(settings.ws_port)
    player = AudioPlayer(lambda v: bridge.broadcast(AmplitudeEvent(v)))

    tracker = build_tracker(settings, ROOT.parent)
    store = GrudgeStore(ROOT / "data" / "bonnington.db")
    main_loop = asyncio.get_running_loop()
    presenter = Presenter(tracker, bridge, britney_count=store.britney_count, mic=settings.mic_source,
                          models_loaded=lambda: state.get("orch") is not None and state["orch"].models_loaded(),
                          defer=lambda fn: main_loop.run_in_executor(None, fn))
    tracker.on_change = presenter.changed
    tracker.on_tool = presenter.tool_ran

    async def play_file(path: str) -> None:
        import soundfile as sf
        data, sr = sf.read(path, dtype="float32", always_2d=False)
        await player.play(Utterance(data, sr, ""))

    settings_path = ROOT / "data" / "settings.json"
    if settings.mic_source == "phone":
        import ssl

        from .audio.phone import PhoneMicSource, ensure_cert, lan_ip
        from .config import ensure_phone_token
        ip = lan_ip()
        cert, key = ensure_cert(ROOT / "data" / "phone", ip)
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(cert, key)
        mic = PhoneMicSource(settings.phone_port, ensure_phone_token(settings, settings_path),
                             ssl_context=tls, lan_ip=ip)
        await mic.start()
        print(f"Phone mic: open {mic.url} on your phone (same Wi-Fi) and enter code {mic.token}", flush=True)
        state["phone_url"] = f"{mic.url}  code {mic.token}"
    else:
        mic = MicSource(device=settings.mic_device)
    deps = Deps(source=mic, wake=SttWake(settings.wake_phrases, settings, min_similarity=settings.wake_similarity),
                turn=TurnDetector(silence_ms=settings.turn_silence_ms), stt=build_stt(settings), brain=Brain(settings.llm_model, tracker=tracker),
                tts=TTSEngine(settings), player=player, bridge=bridge,
                store=store, settings=settings,
                play_file=play_file)
    orch = Orchestrator(deps)
    state["orch"] = orch
    orch.on_user_text = presenter.user_said
    orch.on_reply_done = presenter.reply_done
    controller = LifecycleController(orch, mic, UIProcess(UI_EXE),
                                     idle_unload_s=settings.idle_unload_seconds)
    controller.always_listening = lambda: settings.always_listening
    controller.keep_window = settings.keep_window_open
    kick = orch.on_session_end

    def session_ended() -> None:
        if kick:
            kick()
        presenter.session_ended()
    orch.on_session_end = session_ended

    async def keep_fresh() -> None:
        while True:                       # the clock, "in N days" and project idle times drift
            presenter.refresh()
            await asyncio.sleep(60)
    loop = asyncio.get_running_loop()
    hotkey = HotkeyListener(settings.hotkey, lambda: loop.call_soon_threadsafe(orch.trigger, "hotkey"))

    def set_headphones(on: bool) -> None:
        settings.headphones_mode = on
        save_settings(settings, ROOT / "data" / "settings.json")

    def set_always_listening(on: bool) -> None:
        settings.always_listening = on
        save_settings(settings, ROOT / "data" / "settings.json")
        controller._kick_now()

    state.update(controller=controller, settings=settings, set_headphones=set_headphones,
                 set_always_listening=set_always_listening, loop=loop)
    state["ready"].set()
    await bridge.start()
    hotkey.start()
    try:
        await asyncio.gather(orch.run(), controller.run(), keep_fresh())
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
                set_headphones=state["set_headphones"],
                get_always_listening=lambda: settings.always_listening,
                set_always_listening=state["set_always_listening"], on_quit=lambda: None,
                phone_url=state.get("phone_url"))
    controller.on_level_change = lambda lvl: tray.set_level(lvl.value)
    tray.run()  # returns on Quit; the daemon worker dies with the process


if __name__ == "__main__":
    main()

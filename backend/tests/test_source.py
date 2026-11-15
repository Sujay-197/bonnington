from bonnington.audio.source import MicSource


async def _take(src, n):
    out = []
    async for f in src.frames():
        out.append(f)
        if len(out) == n:
            return out


async def test_frames_flow(stalling_factory):
    fac = stalling_factory(stall_after=None)
    src = MicSource(stream_factory=fac)
    await src.open()
    frames = await _take(src, 5)
    assert len(frames) == 5 and frames[0].shape == (1280,) and str(frames[0].dtype) == "int16"


async def test_recovers_from_stalled_device(stalling_factory):
    fac = stalling_factory(stall_after=3)
    src = MicSource(stream_factory=fac, stall_seconds=0.1, retry_seconds=0.01)
    await src.open()
    frames = await _take(src, 8)
    assert len(frames) == 8 and fac.opens >= 2


async def test_device_name_passed_to_stream(stalling_factory):
    fac = stalling_factory(stall_after=None)
    src = MicSource(device="Nord Buds", stream_factory=fac)
    await src.open()
    await _take(src, 1)
    assert fac.kw["device"] == "Nord Buds" and fac.kw["samplerate"] == 16000


async def test_close_marks_closed(stalling_factory):
    src = MicSource(stream_factory=stalling_factory(stall_after=None))
    await src.open()
    assert src.is_open
    await src.close()
    assert not src.is_open


def test_settings_mic_device_default_none(tmp_path):
    from bonnington.config import load_settings
    assert load_settings(tmp_path / "s.json").mic_device is None


async def test_busy_event_loop_is_not_mistaken_for_a_stall(stalling_factory):
    import asyncio
    import time
    fac = stalling_factory(stall_after=None)
    src = MicSource(stream_factory=fac, stall_seconds=0.1, retry_seconds=0.01)
    await src.open()

    async def hog():          # another task blocks the loop (e.g. speech recognition catching up)
        for _ in range(4):
            await asyncio.sleep(0.02)
            time.sleep(0.3)

    task = asyncio.create_task(hog())
    async for _ in src.frames():
        if task.done():
            break
    assert fac.opens == 1

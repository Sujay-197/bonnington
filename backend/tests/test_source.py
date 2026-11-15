from bonnington.audio.source import MicSource


async def test_mic_source_recovers_from_device_loss(flaky_stream_factory):
    src = MicSource(retry_seconds=0.01, stream_factory=flaky_stream_factory(fail_after=3))
    await src.open()
    frames = []
    async for f in src.frames():
        frames.append(f)
        if len(frames) == 6:
            break
    assert len(frames) == 6 and flaky_stream_factory.opens >= 2 and frames[0].shape == (1280,)


async def test_close_marks_closed(flaky_stream_factory):
    src = MicSource(stream_factory=flaky_stream_factory(fail_after=None))
    await src.open()
    assert src.is_open
    await src.close()
    assert not src.is_open

"""A hung Ollama must not freeze him: every call has a time limit."""

import asyncio

import httpx
import pytest

from bonnington.brain.llm import Brain, BrainUnavailable


def test_the_default_client_has_timeouts():
    timeout = Brain("m").client._client.timeout
    assert timeout.connect is not None and timeout.read is not None


async def test_a_timed_out_warm_up_is_brain_unavailable(fake_ollama):
    fake_ollama.raise_on_chat = httpx.ReadTimeout("slow")
    with pytest.raises(BrainUnavailable):
        await Brain("m", client=fake_ollama).warm()


async def test_a_timed_out_unload_is_brain_unavailable(fake_ollama):
    fake_ollama.raise_on_chat = httpx.ReadTimeout("slow")
    with pytest.raises(BrainUnavailable):
        await Brain("m", client=fake_ollama).unload()


async def test_a_warm_up_that_never_returns_does_not_freeze_waking(rig, monkeypatch):
    import bonnington.orchestrator as orch_mod
    monkeypatch.setattr(orch_mod, "WARM_TIMEOUT_S", 0)   # the rig's frames run faster than real time

    async def hang():
        await asyncio.Event().wait()
    rig.brain.warm = hang
    rig.wake_on_frame(0, "britney")
    rig.speech(frames=range(2, 6))
    rig.stt_final("hi")
    await rig.run_until_idle()
    assert rig.brain_calls == 1 and rig.spoken()

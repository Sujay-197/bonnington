import re

import httpx
import ollama
import pytest

from bonnington.brain.llm import Brain, BrainUnavailable


async def test_stream_reply_streams_and_records_history(fake_ollama):
    fake_ollama.script = ["<mood:smug>Oh, ", "Bonnington. ", "Finally."]
    b = Brain("gemma4:12b", client=fake_ollama)
    out = [c async for c in b.stream_reply("hey")]
    assert "".join(out) == "<mood:smug>Oh, Bonnington. Finally."
    call = fake_ollama.calls[-1]
    assert call["think"] is False and call["stream"] is True and call["keep_alive"] == "30m"
    assert call["model"] == "gemma4:12b" and call["messages"][0]["role"] == "system"
    assert call["messages"][-1] == {"role": "user", "content": "hey"}
    assert b.history[-1] == {"role": "assistant", "content": "<mood:smug>Oh, Bonnington. Finally."}


async def test_connection_error_raises_brain_unavailable(fake_ollama):
    fake_ollama.raise_on_chat = httpx.ConnectError("refused")
    with pytest.raises(BrainUnavailable):
        [c async for c in Brain("gemma4:12b", client=fake_ollama).stream_reply("hey")]


async def test_missing_model_raises_brain_unavailable(fake_ollama):
    fake_ollama.raise_on_chat = ollama.ResponseError("model not found", 404)
    with pytest.raises(BrainUnavailable):
        await Brain("gemma4:12b", client=fake_ollama).warm()


async def test_unload_sends_keep_alive_zero(fake_ollama):
    await Brain("gemma4:12b", client=fake_ollama).unload()
    assert fake_ollama.calls[-1]["keep_alive"] == 0


async def test_warm_keeps_alive_30m(fake_ollama):
    await Brain("gemma4:12b", client=fake_ollama).warm()
    assert fake_ollama.calls[-1]["keep_alive"] == "30m"


def test_history_trimmed_to_20(fake_ollama):
    b = Brain("gemma4:12b", client=fake_ollama)
    for i in range(30):
        b._append("user", str(i))
    msgs = b._messages()
    assert len(msgs) == 21 and msgs[0]["role"] == "system" and msgs[-1]["content"] == "29"


def test_reset_session_clears_history(fake_ollama):
    b = Brain("gemma4:12b", client=fake_ollama)
    b._append("user", "x")
    b.reset_session()
    assert b.history == []


@pytest.mark.hw
async def test_real_ollama_replies_with_mood_tag():
    out = "".join([c async for c in Brain("gemma4:12b").stream_reply("Hey. Say hi.")])
    assert re.match(r"\s*<mood:(neutral|amused|annoyed|smug|serious|disappointed)>", out)

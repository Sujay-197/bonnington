import pytest

from bonnington.lifecycle import Level, next_level

BASE = dict(fullscreen=False, mic_busy=False, manual_dnd=False, wake_requested=False,
            idle_s=0, idle_unload_s=600)


@pytest.mark.parametrize("kw,expected", [
    (dict(fullscreen=True), Level.ASLEEP),
    (dict(mic_busy=True), Level.ASLEEP),
    (dict(manual_dnd=True), Level.ASLEEP),
    (dict(wake_requested=True), Level.AWAKE),
    (dict(), Level.DORMANT),
])
def test_next_level_from_dormant(kw, expected):
    assert next_level(Level.DORMANT, **{**BASE, **kw}) == expected


def test_awake_unloads_after_10_min():
    assert next_level(Level.AWAKE, **{**BASE, "idle_s": 600}) == Level.DORMANT


def test_awake_stays_awake_before_10_min():
    assert next_level(Level.AWAKE, **{**BASE, "idle_s": 599}) == Level.AWAKE


def test_asleep_returns_to_dormant_when_clear():
    assert next_level(Level.ASLEEP, **BASE) == Level.DORMANT


def test_fullscreen_beats_wake():
    assert next_level(Level.DORMANT, **{**BASE, "fullscreen": True, "wake_requested": True}) == Level.ASLEEP


async def test_controller_closes_mic_when_asleep_and_unloads_when_dormant(fake_world):
    c = fake_world.controller()
    fake_world.wake()
    await fake_world.tick()
    assert c.level == Level.AWAKE and fake_world.ui.shown
    fake_world.fullscreen = True
    await fake_world.tick()
    assert c.level == Level.ASLEEP and not fake_world.mic.is_open
    assert fake_world.orch.unloaded and not fake_world.ui.shown


async def test_idle_timeout_goes_dormant_and_keeps_mic(fake_world):
    c = fake_world.controller()
    fake_world.wake()
    await fake_world.tick()
    fake_world.now = 601
    await fake_world.tick()
    assert c.level == Level.DORMANT and fake_world.mic.is_open
    assert fake_world.orch.unloaded and not fake_world.ui.shown


async def test_hotkey_wakes_from_asleep_despite_game(fake_world):
    c = fake_world.controller()
    fake_world.fullscreen = True
    await fake_world.tick()
    assert c.level == Level.ASLEEP and not fake_world.mic.is_open
    fake_world.wake()
    await fake_world.tick()
    assert c.level == Level.AWAKE and fake_world.mic.is_open
    await fake_world.tick()
    assert c.level == Level.AWAKE          # probes bypassed until next idle
    fake_world.now = 601
    await fake_world.tick()
    await fake_world.tick()
    assert c.level == Level.ASLEEP


async def test_dnd_sleeps(fake_world):
    c = fake_world.controller()
    c.set_dnd(True)
    await fake_world.tick()
    assert c.level == Level.ASLEEP
    c.set_dnd(False)
    await fake_world.tick()
    assert c.level == Level.DORMANT and fake_world.mic.is_open


def test_controller_registers_wake_callback(fake_world):
    fake_world.controller()
    assert fake_world.orch.on_wake_requested is not None

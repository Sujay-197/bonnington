import pytest

from bonnington.sysprobe import _busy_state, mic_in_use_by_other


def test_mic_probe_excludes_own_exe(fake_registry):
    fake_registry.add("NonPackaged/C:#py#python.exe", last_stop=0)
    assert mic_in_use_by_other("C:#py#python.exe", reg=fake_registry) is False
    fake_registry.add("NonPackaged/C:#Discord#Discord.exe", last_stop=0)
    assert mic_in_use_by_other("C:#py#python.exe", reg=fake_registry) is True


def test_finished_use_is_not_busy(fake_registry):
    fake_registry.add("NonPackaged/C:#Discord#Discord.exe", last_stop=133000000)
    assert mic_in_use_by_other("C:#py#python.exe", reg=fake_registry) is False


def test_never_used_is_not_busy(fake_registry):
    fake_registry.add("Microsoft.WindowsSoundRecorder", last_stop=0, last_start=0)
    assert mic_in_use_by_other("x", reg=fake_registry) is False


def test_own_exe_list(fake_registry):
    fake_registry.add("NonPackaged/C:#base#python.exe", last_stop=0)
    assert mic_in_use_by_other(["C:#venv#python.exe", "C:#base#python.exe"], reg=fake_registry) is False


@pytest.mark.parametrize("state,busy", [(1, False), (2, True), (3, True), (4, True), (5, False)])
def test_notification_state_mapping(state, busy):
    assert _busy_state(state) is busy

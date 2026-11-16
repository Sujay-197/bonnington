from datetime import datetime, timedelta

from bonnington.store import GrudgeStore


def test_britney_increments_and_bonnington_does_not(tmp_path):
    st = GrudgeStore(tmp_path / "b.db")
    t0 = datetime(2026, 11, 15, 22, 0)
    assert st.record_summons("britney", t0).britney_count == 1
    ctx = st.record_summons("bonnington", t0 + timedelta(seconds=30))
    assert ctx.britney_count == 1 and ctx.seconds_since_last == 30.0


def test_first_summons_has_no_previous(tmp_path):
    ctx = GrudgeStore(tmp_path / "b.db").record_summons("hotkey", datetime(2026, 11, 15, 9, 0))
    assert ctx.seconds_since_last is None and ctx.summons_last_10min == 1


def test_summons_last_10min_counts_window(tmp_path):
    st = GrudgeStore(tmp_path / "b.db")
    t0 = datetime(2026, 11, 15, 22, 0)
    for i in range(5):
        st.record_summons("britney", t0 + timedelta(minutes=i))
    ctx = st.record_summons("hotkey", t0 + timedelta(minutes=12))
    assert ctx.summons_last_10min == 4 and ctx.britney_count == 5


def test_count_persists_across_instances(tmp_path):
    GrudgeStore(tmp_path / "b.db").record_summons("britney", datetime.now())
    assert GrudgeStore(tmp_path / "b.db").britney_count() == 1


def test_count_can_be_read_from_another_thread(tmp_path):
    import threading
    st = GrudgeStore(tmp_path / "b.db")
    st.record_summons("britney", datetime.now())
    out = []
    t = threading.Thread(target=lambda: out.append(st.britney_count()))
    t.start()
    t.join()
    assert out == [1]


def test_saying_britney_mid_conversation_counts_but_is_not_a_summons(tmp_path):
    st = GrudgeStore(tmp_path / "b.db")
    t0 = datetime(2026, 11, 15, 22, 0)
    st.record_summons("hotkey", t0)
    assert st.record_mention(t0 + timedelta(seconds=20)) == 1
    assert st.record_mention(t0 + timedelta(seconds=40)) == 2
    assert st.britney_count() == 2
    ctx = st.record_summons("hotkey", t0 + timedelta(seconds=60))
    assert ctx.britney_count == 2 and ctx.summons_last_10min == 2 and ctx.seconds_since_last == 60.0
    assert st.summons_count() == 2

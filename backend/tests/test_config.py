from bonnington.config import load_settings, save_settings


def test_load_settings_creates_defaults(tmp_path):
    s = load_settings(tmp_path / "settings.json")
    assert s.followup_seconds == 8.0 and s.idle_unload_seconds == 600.0
    assert s.llm_model == "gemma4:12b" and s.headphones_mode is False
    assert (tmp_path / "settings.json").exists()


def test_load_settings_ignores_unknown_keys(tmp_path):
    p = tmp_path / "s.json"
    p.write_text('{"ws_port": 9000, "bogus": 1}')
    assert load_settings(p).ws_port == 9000


def test_save_then_load_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    s = load_settings(p)
    s.headphones_mode = True
    save_settings(s, p)
    assert load_settings(p).headphones_mode is True


def test_phone_mic_defaults(tmp_path):
    s = load_settings(tmp_path / "s.json")
    assert s.mic_source == "device" and s.phone_port == 8766 and s.phone_token == ""


def test_ensure_phone_token_generates_once_and_saves(tmp_path):
    from bonnington.config import ensure_phone_token
    p = tmp_path / "s.json"
    s = load_settings(p)
    t = ensure_phone_token(s, p)
    assert len(t) == 6 and t.isdigit() and load_settings(p).phone_token == t
    assert ensure_phone_token(load_settings(p), p) == t


def test_old_long_token_is_replaced_by_a_code(tmp_path):
    from bonnington.config import ensure_phone_token
    p = tmp_path / "s.json"
    s = load_settings(p)
    s.phone_token = "Zx9-long-old-token_abc"
    assert ensure_phone_token(s, p).isdigit()

import json

from bonnington.events import (AmplitudeEvent, ClearSubtitlesEvent, MoodEvent, StateEvent,
                               SubtitleLineEvent, UserFinalEvent, UserPartialEvent)


def test_subtitle_event_json():
    e = SubtitleLineEvent(id=3, text="Hello.", duration_ms=900, word_offsets_ms=[0])
    assert json.loads(e.to_json()) == {"type": "subtitle_line", "id": 3, "text": "Hello.",
                                        "duration_ms": 900, "word_offsets_ms": [0]}


def test_amplitude_rounded():
    assert json.loads(AmplitudeEvent(0.123456).to_json())["value"] == 0.123


def test_type_names():
    assert json.loads(StateEvent("thinking").to_json()) == {"type": "state", "value": "thinking"}
    assert json.loads(MoodEvent("smug").to_json())["type"] == "mood"
    assert json.loads(UserPartialEvent("hey").to_json())["type"] == "user_partial"
    assert json.loads(UserFinalEvent("hey").to_json())["type"] == "user_final"
    assert json.loads(ClearSubtitlesEvent().to_json()) == {"type": "clear_subtitles"}

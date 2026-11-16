"""Text-to-speech in Bonnington's locked voice, plus subtitle word timing."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .config import Settings

_SPACE_WEIGHT = 0.3
_COMMA_PAUSE = 2.0
_SENTENCE_PAUSE = 4.0


@dataclass
class Utterance:
    """Audio for one sentence. Either complete (`pcm`) or streamed: chunks arrive on `stream`, None ends it."""

    pcm: np.ndarray
    sample_rate: int
    text: str
    word_offsets_ms: list[int] = field(default_factory=list)
    stream: queue.Queue | None = None
    est_duration_ms: int | None = None

    @property
    def duration_ms(self) -> int:
        if self.est_duration_ms is not None:
            return self.est_duration_ms
        return int(round(len(self.pcm) / self.sample_rate * 1000))


def estimate_word_offsets(text: str, duration_ms: int) -> list[int]:
    """Spread words over the audio by character length, with extra time after punctuation."""
    words = text.split()
    if not words:
        return []
    starts: list[float] = []
    pos = 0.0
    for w in words:
        starts.append(pos)
        pos += len(w) + _SPACE_WEIGHT
        if w[-1] in ",;:":
            pos += _COMMA_PAUSE
        elif w[-1] in ".!?…":
            pos += _SENTENCE_PAUSE
    return [int(s / pos * duration_ms) for s in starts]


SECONDS_PER_CHAR = 0.065  # starting guess for speech length; refined from real audio
CHUNK_STEPS = 8           # ~0.67 s of audio per streamed chunk


class TTSEngine:
    """Qwen3-TTS Base (faster-qwen3-tts, CUDA graphs) in the locked reference voice, streamed chunk by chunk."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._ref_text = ""
        self._gen_lock = threading.Lock()   # the model is not re-entrant: one generation at a time
        # Bumped by cancel(). A sentence remembers the number from when it was asked for, so one still
        # waiting for the model when he is interrupted is dropped instead of generated for nobody.
        self._epoch = 0
        self._s_per_char = SECONDS_PER_CHAR

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_qwen3_tts import FasterQwen3TTS

        self._ref_text = Path(self.settings.voice_ref_text).read_text(encoding="utf-8").strip()
        self._model = FasterQwen3TTS.from_pretrained(self.settings.tts_model, local_files_only=True)
        u = self.synth("Ready.")  # first call captures the CUDA graphs
        while u.stream.get() is not None:
            pass

    def unload(self) -> None:
        if self._model is None:
            return
        import gc

        import torch
        self.cancel()
        with self._gen_lock:
            self._model = None
        gc.collect()
        torch.cuda.empty_cache()

    def cancel(self) -> None:
        """Stop the generation in progress and drop every sentence already asked for (he was interrupted)."""
        self._epoch += 1

    def synth(self, sentence: str) -> Utterance:
        """Start speaking `sentence`. Returns as soon as the first chunk of audio exists."""
        if self._model is None:
            raise RuntimeError("TTSEngine.synth called before load()")
        epoch = self._epoch                 # taken before waiting, so a cancel while waiting counts
        est = max(300, int(len(sentence) * self._s_per_char * 1000))
        u = Utterance(np.zeros(0, np.float32), 24000, sentence,
                      estimate_word_offsets(sentence, est), stream=queue.Queue(), est_duration_ms=est)
        self._gen_lock.acquire()            # wait for the previous sentence to finish generating
        if epoch != self._epoch or self._model is None:   # interrupted (or unloaded) while waiting
            self._gen_lock.release()
            u.stream.put(None)
            return u
        first = threading.Event()
        threading.Thread(target=self._generate, args=(u, first, epoch), daemon=True).start()
        first.wait()
        return u

    def _generate(self, u: Utterance, first: threading.Event, epoch: int) -> None:
        samples = 0
        try:
            gen = self._model.generate_voice_clone_streaming(
                text=u.text, language="English", ref_audio=self.settings.voice_ref_wav,
                ref_text=self._ref_text, chunk_size=CHUNK_STEPS)
            try:
                for chunk, sr, _timing in gen:
                    u.sample_rate = int(sr)
                    pcm = np.asarray(chunk, dtype=np.float32).reshape(-1)
                    samples += len(pcm)
                    u.stream.put(pcm)
                    first.set()
                    if self._epoch != epoch:
                        break
            finally:
                gen.close()
            if samples and self._epoch == epoch and len(u.text) >= 8:
                actual = samples / u.sample_rate / len(u.text)
                self._s_per_char = 0.5 * self._s_per_char + 0.5 * actual
        except Exception:
            import logging
            logging.getLogger(__name__).exception("speech generation failed")
        finally:
            u.stream.put(None)
            first.set()
            self._gen_lock.release()

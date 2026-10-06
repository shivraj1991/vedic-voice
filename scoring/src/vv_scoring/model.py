"""Phoneme posterior model (wav2vec2 XLSR-53 fine-tuned on espeak IPA, ONNX).

Why this model: it is multilingual (53 languages incl. Hindi-like phones such as
retroflex and aspirated stops), outputs phones rather than words (so it does not
"autocorrect" a mispronunciation into a dictionary word), and is Apache-2.0.
We run it with onnxruntime instead of PyTorch to keep the Lambda image small.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import onnxruntime as ort

FRAME_SECONDS = 0.02  # wav2vec2 conv stack stride: 320 samples at 16 kHz
BLANK = "<pad>"  # the CTC blank token in this vocabulary


@dataclass(frozen=True)
class Posteriors:
    """Frame-level log posteriors, shape (T, V)."""

    log_probs: np.ndarray
    vocab: dict[str, int]

    @property
    def n_frames(self) -> int:
        return int(self.log_probs.shape[0])

    def greedy(self) -> list[tuple[str, int]]:
        """Greedy CTC decode -> [(token, frame)], for debugging and match checks."""
        inv = {i: t for t, i in self.vocab.items()}
        ids = self.log_probs.argmax(axis=1)
        out, prev = [], -1
        for f, i in enumerate(ids):
            if i != prev and i != self.vocab[BLANK]:
                out.append((inv[int(i)], f))
            prev = i
        return out


class PhonemeModel:
    """Thin onnxruntime wrapper. Load once per process (Lambda container reuse)."""

    def __init__(self, model_dir: str | Path, onnx_file: str = "model.onnx", threads: int = 0):
        model_dir = Path(model_dir)
        self.vocab: dict[str, int] = json.loads((model_dir / "vocab.json").read_text("utf-8"))
        opts = ort.SessionOptions()
        if threads:
            opts.intra_op_num_threads = threads
        self.session = ort.InferenceSession(
            str(model_dir / onnx_file),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        self.input_name = self.session.get_inputs()[0].name

    def posteriors(self, audio: np.ndarray) -> Posteriors:
        # Wav2Vec2FeatureExtractor(do_normalize=True): zero mean, unit variance.
        x = (audio - audio.mean()) / np.sqrt(audio.var() + 1e-7)
        logits = self.session.run(None, {self.input_name: x[None, :].astype(np.float32)})[0][0]
        logits = logits.astype(np.float64)
        m = logits.max(axis=1, keepdims=True)
        log_probs = logits - (m + np.log(np.exp(logits - m).sum(axis=1, keepdims=True)))
        return Posteriors(log_probs=log_probs, vocab=self.vocab)

"""Vedic Voice pronunciation scoring.

Pipeline: decode audio -> multilingual phoneme posteriors (wav2vec2 XLSR-53
espeak, ONNX) -> CTC forced alignment of the expected Sanskrit phonemes ->
goodness-of-pronunciation (GOP) per phoneme using curated confusion sets ->
per-word score and a plain-language issue, calibrated against the reference
recording of the same shloka.
"""

__version__ = "0.1.0"

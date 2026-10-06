"""Build a labelled synthetic test set (formant-synth voices + perturbations).

Synthetic voices are crude, so results here only show whether a scorer
behaves sensibly (catches gross errors, ignores voice/tempo changes). Real
accuracy must come from real recordings labelled by the advisor.
"""

import shutil
from pathlib import Path

import yaml

from spike.manifest import Attempt, Manifest, dump
from vv_scoring import perturb
from vv_scoring.audio_io import save_wav
from vv_scoring.synth import Speaker, synthesize
from vv_scoring.types import Word

# Correct chants by different voices.
SPEAKERS = {
    "female-slow": Speaker(f0=210, formant_scale=1.17, tempo=1.25, seed=3),
    "male-fast": Speaker(f0=100, formant_scale=0.95, tempo=0.85, seed=5),
    "child": Speaker(f0=260, formant_scale=1.25, tempo=1.1, seed=8),
    "male-mid": Speaker(f0=140, formant_scale=1.03, seed=9),
}
# Pronunciation errors rendered by a non-reference voice: (position, wrong IAST, label).
PHONE_ERRORS = [
    (9, "dhimahi", "too_short"),  # ī → i
    (13, "pracodayat", "too_short"),  # ā → a
    (7, "bargo", "sound_mismatch"),  # bh → b (aspiration dropped)
    (6, "varenyaṃ", "sound_mismatch"),  # ṇ → n (retroflex → dental)
    (5, "shavitur", "sound_mismatch"),  # s → sh-like
]


def build(fixture: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture, out / fixture.name)
    words = [Word(i, w) for i, w in enumerate(yaml.safe_load(fixture.read_text("utf-8"))["words"])]
    ref, marks = synthesize(words, Speaker())
    save_wav(out / "reference.wav", ref)
    m = Manifest(
        out, words, out / "reference.wav", marks, "synthetic (generated)", "vv_scoring.synth"
    )

    def add(aid, y, group, labels, note=""):
        save_wav(out / f"{aid}.wav", y)
        m.attempts.append(Attempt(aid, out / f"{aid}.wav", group, labels, note=note))

    ok = {w.position: "ok" for w in words}
    for name, spk in SPEAKERS.items():
        add(f"voice-{name}", synthesize(words, spk)[0], "voice (correct)", ok)

    base_spk = SPEAKERS["male-mid"]
    base, base_marks = synthesize(words, base_spk)
    for label, (fn, arg) in {
        "tempo-0.8": ("tempo", 0.8),
        "tempo-1.25": ("tempo", 1.25),
        "pitch+3": ("pitch", 3),
        "pitch-3": ("pitch", -3),
        "noise-20db": ("noise", 20),
        "noise-10db": ("noise", 10),
    }.items():
        y, _, labels = getattr(perturb, fn)(base, base_marks, arg)
        add(f"neutral-{label}", y, "neutral change (correct)", labels)

    for pos in (2, 5, 11):
        y, _, labels = perturb.delete_word(base, base_marks, pos)
        add(f"skip-{words[pos].iast}", y, "skipped word", labels)
    for pos in (1, 9, 13):
        y, _, labels = perturb.shorten_word(base, base_marks, pos, 0.5)
        add(f"rushed-{words[pos].iast}", y, "rushed word", labels)
    for pos, other in ((4, 11), (8, 10), (12, 3)):
        y, _, labels = perturb.substitute_word(base, base_marks, pos, other)
        add(f"wrong-{words[pos].iast}", y, "wrong word", labels)

    for pos, wrong, code in PHONE_ERRORS:
        changed = [Word(w.position, wrong) if w.position == pos else w for w in words]
        add(
            f"phone-{wrong}",
            synthesize(changed, base_spk)[0],
            "sound error",
            ok | {pos: code},
            note=f"{words[pos].iast} → {wrong}",
        )

    path = out / "manifest.yaml"
    dump(m, fixture.name, path)
    return path

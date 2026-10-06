from pathlib import Path

import pytest
import yaml

from vv_scoring.synth import Speaker, synthesize
from vv_scoring.types import Word

FIXTURE = Path(__file__).parent.parent / "spike" / "fixtures" / "gayatri.yaml"


@pytest.fixture(scope="session")
def words() -> list[Word]:
    data = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    return [Word(i, w) for i, w in enumerate(data["words"])]


@pytest.fixture(scope="session")
def reference(words):
    """(audio, marks) for a synthetic reference reciter."""
    return synthesize(words, Speaker())


@pytest.fixture(scope="session")
def other_speaker(words):
    """A different, correct, slightly slower and higher voice."""
    return synthesize(words, Speaker(f0=170, formant_scale=1.1, tempo=1.1, seed=11))

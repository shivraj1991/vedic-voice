"""Plain data types shared by every scorer, so scorers are interchangeable."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Word:
    """One surface word of a shloka, as chanted (sandhi already applied)."""

    position: int
    iast: str


@dataclass(frozen=True)
class WordMark:
    """Where a word sits in a recording, in seconds from the start of the file."""

    position: int
    start_s: float
    end_s: float

    def __post_init__(self) -> None:
        if self.end_s <= self.start_s:
            raise ValueError(f"word {self.position}: end_s must be after start_s")


@dataclass
class WordScore:
    position: int
    iast: str
    score: int  # 0–100
    issue_code: str | None = None
    issue_text: str | None = None
    # Diagnostics for the spike report; not shown to learners.
    details: dict[str, float] = field(default_factory=dict)


@dataclass
class ScoreResult:
    overall: int  # 0–100
    words: list[WordScore]
    scorer: str
    scorer_version: str
    details: dict[str, float] = field(default_factory=dict)

"""SQLAlchemy models: the Vedic Voice data model (schema draft in CLAUDE.md).

Content rules are enforced as close to the data as possible:
- `verified` rows must say who verified them and when (CHECK constraints).
- Editing verified content resets `verified` (DB triggers, see migration 0001),
  so no code path can forget it.
- Learner reads go through the `verified_shlokas` view.
Role checks (only advisors verify) and `content_audit` rows are written by the
data-access layer (`vv_backend.content`), because the DB cannot see Clerk roles.

Conventions: UUID primary keys generated in Postgres (gen_random_uuid), all
timestamps `timestamptz` in UTC, no names/emails of people (Clerk IDs only).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    pass


Base.metadata.naming_convention = NAMING


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created() -> Mapped[dt.datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _updated() -> Mapped[dt.datetime]:
    # Kept current by the set_updated_at() trigger (migration 0001).
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# --- content -----------------------------------------------------------------


class Source(Base):
    """A text corpus, audio collection, tool or model we use, with its license."""

    __tablename__ = "sources"
    __table_args__ = (CheckConstraint("kind IN ('text', 'audio', 'tool', 'model')", name="kind"),)

    id: Mapped[uuid.UUID] = _pk()
    key: Mapped[str] = mapped_column(String(100), unique=True)  # id in data/sources.yaml
    kind: Mapped[str] = mapped_column(String(10))
    name: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str] = mapped_column(Text)
    license_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[dt.date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)


class Shloka(Base):
    __tablename__ = "shlokas"
    __table_args__ = (
        CheckConstraint(
            "NOT verified OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="verified_has_reviewer",
        ),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="slug_format"),
    )

    id: Mapped[uuid.UUID] = _pk()
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    devanagari: Mapped[str] = mapped_column(Text)
    iast: Mapped[str] = mapped_column(Text)
    translation: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"))
    source_ref: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    verified_by: Mapped[str | None] = mapped_column(String(64))  # Clerk user ID
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    review_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    source: Mapped[Source] = relationship()
    words: Mapped[list[ShlokaWord]] = relationship(
        back_populates="shloka", order_by="ShlokaWord.position", cascade="all, delete-orphan"
    )


class ShlokaWord(Base):
    """A word as recited (saṃhitā form) — the unit learners are scored on."""

    __tablename__ = "shloka_words"
    __table_args__ = (
        UniqueConstraint("shloka_id", "position", name="uq_shloka_words_shloka_position"),
        CheckConstraint("position >= 0", name="position_nonneg"),
    )

    id: Mapped[uuid.UUID] = _pk()
    shloka_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shlokas.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    surface_iast: Mapped[str] = mapped_column(String(200))
    surface_devanagari: Mapped[str] = mapped_column(String(200))
    # Filled by the scoring service when a reference is analysed (not by the seed).
    expected_phonemes: Mapped[list | None] = mapped_column(JSONB)

    shloka: Mapped[Shloka] = relationship(back_populates="words")
    analyses: Mapped[list[WordAnalysis]] = relationship(
        back_populates="word", order_by="WordAnalysis.position", cascade="all, delete-orphan"
    )


class WordAnalysis(Base):
    """One pada of a recited word: split, grammar, meaning, explanation.

    `morphology` holds the rule-based proposal and all candidates (vv_content);
    the advisor's choice replaces `proposed`. The LLM only fills `explanation`.
    """

    __tablename__ = "word_analyses"
    __table_args__ = (
        UniqueConstraint("shloka_word_id", "position", name="uq_word_analyses_word_position"),
        CheckConstraint(
            "NOT verified OR (verified_by IS NOT NULL AND verified_at IS NOT NULL)",
            name="verified_has_reviewer",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    shloka_word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shloka_words.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(Integer)
    pada_iast: Mapped[str] = mapped_column(String(200))
    lemma: Mapped[str | None] = mapped_column(String(200))
    morphology: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    analysis_tool: Mapped[str | None] = mapped_column(String(50))
    analysis_tool_version: Mapped[str | None] = mapped_column(String(20))
    meaning: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    explanation_model: Mapped[str | None] = mapped_column(String(100))
    explanation_prompt_version: Mapped[str | None] = mapped_column(String(20))
    verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    verified_by: Mapped[str | None] = mapped_column(String(64))
    verified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _created()
    updated_at: Mapped[dt.datetime] = _updated()

    word: Mapped[ShlokaWord] = relationship(back_populates="analyses")


# --- audio -------------------------------------------------------------------


class AudioAsset(Base):
    __tablename__ = "audio_assets"
    __table_args__ = (
        CheckConstraint("kind IN ('reference', 'test', 'user_consented')", name="kind"),
        CheckConstraint(
            "NOT is_active_reference OR kind = 'reference'", name="active_is_reference"
        ),
        CheckConstraint("duration_ms IS NULL OR duration_ms > 0", name="duration_positive"),
        CheckConstraint("sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        # Public test recordings must carry their license and attribution.
        CheckConstraint(
            "kind <> 'test' OR (license IS NOT NULL AND attribution IS NOT NULL)",
            name="test_has_license",
        ),
        # At most one active reference recording per shloka.
        Index(
            "uq_audio_assets_active_reference",
            "shloka_id",
            unique=True,
            postgresql_where=text("is_active_reference"),
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    shloka_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shlokas.id", ondelete="RESTRICT"))
    kind: Mapped[str] = mapped_column(String(20))
    r2_key: Mapped[str] = mapped_column(String(300), unique=True)
    source_url: Mapped[str | None] = mapped_column(Text)
    license: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    reciter: Mapped[str | None] = mapped_column(String(200))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    codec: Mapped[str | None] = mapped_column(String(20))
    sample_rate: Mapped[int | None] = mapped_column(Integer)
    sha256: Mapped[str | None] = mapped_column(String(64))
    is_active_reference: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    verified: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[dt.datetime] = _created()


class AudioWordMark(Base):
    """Word timings inside a recording (reference alignment, advisor-corrected)."""

    __tablename__ = "audio_word_marks"
    __table_args__ = (CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="span"),)

    audio_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="CASCADE"), primary_key=True
    )
    shloka_word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shloka_words.id", ondelete="CASCADE"), primary_key=True
    )
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)


class WordLabel(Base):
    """Advisor ground truth: was this word in this recording pronounced correctly?"""

    __tablename__ = "word_labels"
    __table_args__ = (
        UniqueConstraint(
            "audio_asset_id", "shloka_word_id", "labeled_by", name="uq_word_labels_per_labeler"
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    audio_asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="CASCADE")
    )
    shloka_word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shloka_words.id", ondelete="CASCADE")
    )
    ok: Mapped[bool] = mapped_column(Boolean)
    issue_code: Mapped[str | None] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    labeled_by: Mapped[str] = mapped_column(String(64))
    labeled_at: Mapped[dt.datetime] = _created()


# --- learners ------------------------------------------------------------------


class User(Base):
    """A learner. No email or name: Clerk holds identity, we hold the Clerk ID only."""

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "NOT recording_consent OR (consent_version IS NOT NULL AND consent_at IS NOT NULL)",
            name="consent_recorded",
        ),
    )

    id: Mapped[uuid.UUID] = _pk()
    clerk_user_id: Mapped[str] = mapped_column(String(64), unique=True)
    timezone: Mapped[str] = mapped_column(String(64), server_default=text("'UTC'"))
    recording_consent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    consent_version: Mapped[str | None] = mapped_column(String(20))
    consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = _created()


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        CheckConstraint("overall_score BETWEEN 0 AND 100", name="score_range"),
        CheckConstraint("duration_ms IS NULL OR duration_ms > 0", name="duration_positive"),
        Index("ix_attempts_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    shloka_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("shlokas.id", ondelete="RESTRICT"))
    reference_audio_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("audio_assets.id", ondelete="SET NULL")
    )
    # Only set when the learner consented to keep the recording.
    recording_r2_key: Mapped[str | None] = mapped_column(String(300))
    overall_score: Mapped[int] = mapped_column(SmallInteger)
    scorer_version: Mapped[str] = mapped_column(String(40))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = _created()


class AttemptWordScore(Base):
    __tablename__ = "attempt_word_scores"
    __table_args__ = (CheckConstraint("score BETWEEN 0 AND 100", name="score_range"),)

    attempt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("attempts.id", ondelete="CASCADE"), primary_key=True
    )
    shloka_word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("shloka_words.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[int] = mapped_column(SmallInteger)
    issue_code: Mapped[str | None] = mapped_column(String(40))
    issue_text: Mapped[str | None] = mapped_column(Text)


# --- audit ---------------------------------------------------------------------


class ContentAudit(Base):
    """Append-only history of every content change (who, what, before/after)."""

    __tablename__ = "content_audit"
    __table_args__ = (Index("ix_content_audit_entity", "entity", "entity_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_clerk_id: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(40))
    diff: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    at: Mapped[dt.datetime] = _created()

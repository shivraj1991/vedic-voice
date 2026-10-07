"""Load the initial seed (data/sources.yaml + data/shlokas/*.yaml) into the database.

Idempotent and non-destructive: after seeding, the DB is the content source of
truth (decision 2026-10-06), so existing shlokas are never overwritten; only
missing sources/shlokas are inserted. Sources are upserted by key because
their license metadata may be corrected in sources.yaml. Everything seeded is
`verified = false` and each insert is written to content_audit.

    DATABASE_URL=... uv run python -m vv_backend.seed [--data-dir ../data] [--dry-run]
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from .content import SYSTEM_SEED, audit
from .db.models import Shloka, ShlokaWord, Source, WordAnalysis
from .db.session import make_engine, wait_for_db

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
SECTION_KIND = {"texts": "text", "audio": "audio", "tools": "tool", "models": "model"}


@dataclass
class SeedReport:
    sources_inserted: int = 0
    sources_updated: int = 0
    shlokas_inserted: list[str] = field(default_factory=list)
    shlokas_existing: list[str] = field(default_factory=list)
    shlokas_pending: list[str] = field(default_factory=list)


def _date(value) -> dt.date | None:
    if value is None or isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


def load_sources(session: Session, path: Path, report: SeedReport) -> dict[str, Source]:
    doc = yaml.safe_load(path.read_text("utf-8"))
    by_key = {s.key: s for s in session.scalars(select(Source))}
    for section, kind in SECTION_KIND.items():
        for entry in doc.get(section) or []:
            values = {
                "kind": kind,
                "name": entry["name"],
                "url": entry.get("url"),
                "license": str(entry["license"]),
                "license_url": entry.get("license_url"),
                "retrieved_at": _date(entry.get("retrieved_at")),
                "notes": (entry.get("notes") or "").strip() or None,
            }
            src = by_key.get(entry["id"])
            if src is None:
                src = Source(key=entry["id"], **values)
                session.add(src)
                by_key[src.key] = src
                report.sources_inserted += 1
            elif any(getattr(src, k) != v for k, v in values.items()):
                for k, v in values.items():
                    setattr(src, k, v)
                report.sources_updated += 1
    session.flush()
    return by_key


def load_shloka(session: Session, doc: dict, sources: dict[str, Source]) -> Shloka:
    source = sources.get(doc["source_id"])
    if source is None:
        raise ValueError(f"{doc['slug']}: unknown source_id {doc['source_id']!r} (sources.yaml)")
    shloka = Shloka(
        slug=doc["slug"],
        title=doc["title"],
        devanagari=doc["devanagari"],
        iast=doc["iast"],
        translation=doc.get("translation"),
        source_id=source.id,
        source_ref=doc["source_ref"],
        review_notes=doc.get("review_notes"),
    )
    words = []
    for w in doc["words"]:
        word = ShlokaWord(
            position=w["position"],
            surface_iast=w["surface_iast"],
            surface_devanagari=w["surface_devanagari"],
        )
        shloka.words.append(word)
        words.append(word)
    per_word: dict[int, int] = {}
    for a in doc.get("analyses") or []:
        pos = a["word_position"]
        if pos is None or not 0 <= pos < len(words):
            raise ValueError(f"{doc['slug']}: analysis {a['pada_iast']!r} has no word")
        order = per_word.get(pos, 0)
        per_word[pos] = order + 1
        words[pos].analyses.append(
            WordAnalysis(
                position=order,
                pada_iast=a["pada_iast"],
                lemma=a.get("lemma"),
                morphology=a.get("morphology") or {},
                analysis_tool=doc.get("analysis_tool"),
                analysis_tool_version=doc.get("analysis_tool_version"),
            )
        )
    session.add(shloka)
    session.flush()
    audit(session, SYSTEM_SEED, "shloka", shloka.id, "seed",
          {"slug": shloka.slug, "source": source.key, "words": len(words)})  # fmt: skip
    return shloka


def seed(session: Session, data_dir: Path = DEFAULT_DATA_DIR) -> SeedReport:
    report = SeedReport()
    sources = load_sources(session, data_dir / "sources.yaml", report)
    existing = set(session.scalars(select(Shloka.slug)))
    for path in sorted((data_dir / "shlokas").glob("*.yaml")):
        doc = yaml.safe_load(path.read_text("utf-8"))
        slug = doc["slug"]
        if doc.get("status") != "draft":
            report.shlokas_pending.append(slug)
        elif slug in existing:
            report.shlokas_existing.append(slug)
        else:
            load_shloka(session, doc, sources)
            report.shlokas_inserted.append(slug)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    ap.add_argument("--dry-run", action="store_true", help="roll back instead of committing")
    args = ap.parse_args()
    engine = make_engine()
    wait_for_db(engine)
    with Session(engine) as session:
        report = seed(session, args.data_dir)
        if args.dry_run:
            session.rollback()
        else:
            session.commit()
    print(f"{'DRY RUN - ' if args.dry_run else ''}{report}")


if __name__ == "__main__":
    main()

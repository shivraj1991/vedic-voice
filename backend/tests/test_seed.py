from pathlib import Path

from sqlalchemy import func, select

from vv_backend.content import list_verified_shlokas
from vv_backend.db.models import ContentAudit, Shloka, ShlokaWord, Source, WordAnalysis
from vv_backend.seed import seed

DATA = Path(__file__).resolve().parents[2] / "data"


def count(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_seed_loads_initial_shlokas_unverified(session):
    report = seed(session, DATA)
    assert len(report.shlokas_inserted) == 9
    assert report.shlokas_pending == ["sarve-bhavantu"]  # no open-corpus source yet
    assert session.scalars(select(Shloka.verified).distinct()).all() == [False]
    assert list_verified_shlokas(session) == []
    gayatri = session.scalar(select(Shloka).where(Shloka.slug == "gayatri"))
    assert gayatri.source.key == "gretil-rigveda-aufrecht"
    assert [w.surface_iast for w in gayatri.words][:2] == ["tat", "savitur"]
    assert count(session, ContentAudit) == 9
    # every analysis is attached to a recited word and records the tool
    assert session.scalar(select(func.count()).where(WordAnalysis.analysis_tool.is_(None))) == 0


def test_seed_is_idempotent_and_never_overwrites(session):
    seed(session, DATA)
    words, sources = count(session, ShlokaWord), count(session, Source)
    gayatri = session.scalar(select(Shloka).where(Shloka.slug == "gayatri"))
    gayatri.translation = "edited in console"
    report = seed(session, DATA)
    assert report.shlokas_inserted == [] and len(report.shlokas_existing) == 9
    assert (count(session, ShlokaWord), count(session, Source)) == (words, sources)
    session.refresh(gayatri)
    assert gayatri.translation == "edited in console"

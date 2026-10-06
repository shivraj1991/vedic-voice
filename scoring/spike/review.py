"""Static HTML page to listen to every test recording next to its scores.

Open it locally in a browser; audio files are referenced by relative path,
nothing is uploaded anywhere. The full admin/advisor console comes in
Milestone 3b; this page is the spike-time stand-in.
"""

import html
import os
from pathlib import Path

_CSS = """
:root { --bg:#fbfaf7; --fg:#1d1b18; --muted:#6b665e; --card:#fff; --line:#e6e1d8;
  --good:#1f7a4d; --warn:#b26a00; --bad:#b3261e; --chip:#f2efe9; }
@media (prefers-color-scheme: dark) { :root { --bg:#151412; --fg:#ece8e1; --muted:#a39d93;
  --card:#1e1c19; --line:#34302a; --good:#5cc08b; --warn:#e3a44a; --bad:#ef7a70; --chip:#2a2723; } }
* { box-sizing:border-box } body { margin:0; padding:24px 16px; background:var(--bg); color:var(--fg);
  font:15px/1.5 system-ui, sans-serif } main { max-width:1000px; margin:0 auto }
h1 { font-size:22px; margin:0 0 4px } .muted { color:var(--muted) }
.metrics { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; margin:16px 0 24px }
.metric { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 12px }
.metric b { display:block; font-size:20px } .card { background:var(--card); border:1px solid var(--line);
  border-radius:12px; padding:14px; margin:0 0 12px } .head { display:flex; flex-wrap:wrap; gap:8px 16px;
  align-items:center; justify-content:space-between } audio { width:100%; max-width:360px; height:36px }
.overall { font-weight:700; font-size:18px } .words { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px }
.w { background:var(--chip); border-radius:8px; padding:4px 8px; border:2px solid transparent; cursor:default }
.w small { color:var(--muted); margin-left:4px } .good { color:var(--good) } .warn { color:var(--warn) }
.bad { color:var(--bad) } .truth-bad { border-color:var(--bad) } .issue { margin-top:8px; font-size:14px }
h2 { font-size:16px; margin:24px 0 8px }
"""


def _cls(score: int, threshold: int) -> str:
    return "good" if score >= 90 else ("warn" if score >= threshold else "bad")


def render(
    out_dir: Path, manifest, results: list[dict], metrics: dict, scorer: str, threshold: int
) -> Path:
    def src(p: Path) -> str:
        return html.escape(os.path.relpath(p, out_dir))

    e = html.escape
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>Scoring review</title><style>{_CSS}</style></head><body><main>",
        "<h1>Scoring review</h1>",
        f"<p class='muted'>Scorer <b>{e(scorer)}</b> · pass threshold {threshold} · "
        f"reference license: {e(manifest.ref_license)} · {e(manifest.ref_attribution)}</p>",
        f"<div class='card'><b>Reference</b><br><audio controls preload='none' src='{src(manifest.ref_audio)}'></audio></div>",
        "<div class='metrics'>",
    ]
    for k in (
        "f1",
        "precision",
        "recall",
        "false_alarm_rate",
        "issue_code_accuracy",
        "neutral_mean_overall",
        "spearman_vs_rating",
        "mean_latency_s",
    ):
        parts.append(
            f"<div class='metric'><span class='muted'>{e(k.replace('_', ' '))}</span><b>{e('n/a' if metrics[k] is None else str(metrics[k]))}</b></div>"
        )
    parts.append("</div>")
    rec = metrics["recall_by_error"]
    if rec:
        parts.append(
            "<p class='muted'>Recall by error type: "
            + " · ".join(f"{e(k)} {v}" for k, v in rec.items())
            + "</p>"
        )
    parts.append("<p class='muted'>Chips: colour = score; red outline = labelled as an error.</p>")

    group = None
    for att, r in zip(manifest.attempts, results, strict=True):
        if att.group != group:
            group = att.group
            parts.append(f"<h2>{e(group or 'Attempts')}</h2>")
        chips, issues = [], []
        for w in r["words"]:
            truth = att.labels[w["position"]]
            tip = f"label: {truth}" + (f" · {w['issue_text']}" if w["issue_text"] else "")
            chips.append(
                f"<span class='w {'truth-bad' if truth != 'ok' else ''}' title='{e(tip)}'>{e(w['iast'])}"
                f"<small class='{_cls(w['score'], threshold)}'>{w['score']}</small></span>"
            )
            if w["issue_text"]:
                issues.append(
                    f"<div class='issue {_cls(w['score'], threshold)}'>• {e(w['issue_text'])}</div>"
                )
        parts.append(
            f"<div class='card'><div class='head'><div><b>{e(att.id)}</b> "
            f"<span class='muted'>{e(att.note)}</span></div>"
            f"<span class='overall {_cls(r['overall'], threshold)}'>{r['overall']}</span></div>"
            f"<audio controls preload='none' src='{src(att.audio)}'></audio>"
            f"<div class='words'>{''.join(chips)}</div>{''.join(issues)}</div>"
        )
    parts.append("</main></body></html>")
    path = out_dir / "review.html"
    path.write_text("".join(parts), encoding="utf-8")
    return path

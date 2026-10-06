"""Static review page for the scoring spike.

A single self-contained HTML file (no network, no external scripts) to listen
to every test case next to its reference, hear any word by clicking it, and
mark words the scorer got wrong. Labels stay in the browser (localStorage) and
can be exported as JSON in the same shape as the `word_labels` table, so the
first advisor labels can seed the scoring evaluation.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from vv_scoring.model import FRAME_SECONDS

_CSS = """
:root{--bg:#fbfaf7;--fg:#1d1b16;--muted:#6b665c;--card:#fff;--line:#e4e0d6;
--good:#1f7a4d;--mid:#b07a00;--bad:#b3261e;--accent:#7a3e00}
@media (prefers-color-scheme:dark){:root{--bg:#16140f;--fg:#ece8df;--muted:#a49e92;
--card:#201d17;--line:#36322a;--good:#5cc596;--mid:#e3b341;--bad:#ff8a80;--accent:#f0a35e}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0;padding:16px}
main{max-width:980px;margin:auto}h1{font-size:22px}h2{font-size:18px;margin-top:28px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:10px 0}
.meta{color:var(--muted);font-size:13px}.words{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.w{border:1px solid var(--line);border-radius:6px;padding:2px 8px;cursor:pointer;user-select:none}
.w b{font-weight:600}.w small{color:var(--muted);margin-left:4px}
.g{border-color:var(--good)}.m{border-color:var(--mid)}.b{border-color:var(--bad);border-width:2px}
.t{outline:2px dashed var(--accent);outline-offset:2px}.lab-wrong{background:color-mix(in srgb,var(--bad) 18%,transparent)}
.lab-ok{background:color-mix(in srgb,var(--good) 18%,transparent)}
.issue{color:var(--bad);font-size:13px}audio{width:100%;max-width:460px;height:32px}
.row{display:flex;flex-wrap:wrap;gap:12px;align-items:center}button{font:inherit;padding:4px 10px;
border-radius:6px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
nav a{margin-right:12px;color:var(--accent)}.help{color:var(--muted);font-size:13px}
"""

_JS = """
const KEY='vv-spike-labels';
let labels={};try{labels=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function save(){try{localStorage.setItem(KEY,JSON.stringify(labels))}catch(e){}}
function paint(el){const l=labels[el.dataset.k];el.classList.toggle('lab-wrong',l==='wrong');
 el.classList.toggle('lab-ok',l==='ok')}
document.querySelectorAll('.w').forEach(el=>{paint(el);el.addEventListener('click',ev=>{
 if(ev.shiftKey||ev.altKey){const cur=labels[el.dataset.k];
  labels[el.dataset.k]=ev.shiftKey?(cur==='wrong'?undefined:'wrong'):(cur==='ok'?undefined:'ok');
  if(!labels[el.dataset.k])delete labels[el.dataset.k];save();paint(el);return}
 const a=document.getElementById(el.dataset.a);a.currentTime=el.dataset.s/1000;a.play();
 const stop=+el.dataset.e/1000;const h=()=>{if(a.currentTime>=stop){a.pause();a.removeEventListener('timeupdate',h)}};
 a.addEventListener('timeupdate',h)})});
document.getElementById('export').onclick=()=>{const rows=Object.entries(labels).map(([k,v])=>{
 const [c,i,word]=k.split('|');return{case:c,word_index:+i,word,ok:v==='ok'}});
 const b=new Blob([JSON.stringify(rows,null,1)],{type:'application/json'});const u=URL.createObjectURL(b);
 const x=document.createElement('a');x.href=u;x.download='word_labels.json';x.click()};
document.getElementById('clear').onclick=()=>{if(confirm('Clear all labels?')){labels={};save();
 document.querySelectorAll('.w').forEach(paint)}};
"""

KIND_TITLES = {
    "clean": "Clean: other speakers, same text",
    "deletion": "Deletion: one word cut out",
    "substitute": "Substitution: one word replaced",
    "vowel_short": "Vowel shortened",
    "noise": "Noise: 10 dB SNR",
    "wrong_text": "Wrong text (audio of another text)",
}


def _cls(score: int) -> str:
    return "g" if score >= 85 else "m" if score >= 70 else "b"


def _words(case_id: str, audio_id: str, words: list[dict], target: int | None, labels=True) -> str:
    chips = []
    for w in words:
        k = f"{case_id}|{w['index']}|{w['text']}"
        cls = f"w {_cls(w['score'])}" + (" t" if w["index"] == target else "")
        tip = html.escape(w.get("issue_text") or "")
        chips.append(
            f'<span class="{cls}" title="{tip}" data-a="{audio_id}" data-s="{w["start_ms"]}" '
            f'data-e="{w["end_ms"]}" data-k="{html.escape(k) if labels else ""}"><b>'
            f"{html.escape(w['text'])}</b><small>{w['score']}</small></span>"
        )
    return '<div class="words">' + "".join(chips) + "</div>"


def _ref_words(an) -> list[dict]:
    out = []
    for wi, text in enumerate(an.words):
        us = [u for u in an.units if u.word == wi]
        out.append(
            {"index": wi, "text": text, "score": 100,
             "start_ms": int(us[0].start * FRAME_SECONDS * 1000),
             "end_ms": int(us[-1].end * FRAME_SECONDS * 1000)}
        )  # fmt: skip
    return out


def write_review(path: Path, cases, rows, refs, analyses, rec_by_id) -> None:
    row_by_case = {r["case"]: r for r in rows}
    parts = [
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Scoring Spike Review</title><style>{_CSS}</style></head><body><main>",
        "<h1>Vedic Voice — scoring spike review</h1>",
        "<p class=help>Click a word to hear it. <b>Shift-click</b> marks a word as really "
        "mispronounced, <b>Alt-click</b> as fine. Dashed outline = the word we deliberately "
        "broke. Border: green ≥85, amber ≥70, red &lt;70. Hover a word for its issue text.</p>",
        "<div class=row><button id=export>Export labels (JSON)</button>"
        "<button id=clear>Clear labels</button></div><nav>",
    ]
    parts += [f'<a href="#{k}">{t}</a>' for k, t in KIND_TITLES.items()]
    parts.append("</nav>")
    for kind, title in KIND_TITLES.items():
        kc = [c for c in cases if c.kind == kind]
        if not kc:
            continue
        parts.append(f'<h2 id="{kind}">{title} ({len(kc)})</h2>')
        for c in kc:
            r = row_by_case[c.id]
            res = r["result"]
            ref_id = c.reference_id
            ref_an = analyses[ref_id]
            learner = rec_by_id[c.learner_id]
            issues = "".join(
                f"<div class=issue>{html.escape(w['issue_text'])}</div>"
                for w in res["words"]
                if w.get("issue_text")
            )
            parts.append(
                f"<div class=card><div class=row><b>{html.escape(c.id)}</b>"
                f"<span class=meta>overall {res['overall']} · match {res['match_confidence']}"
                f"{' · ' + html.escape(c.note) if c.note else ''}</span></div>"
                f"<div class=meta>Learner ({html.escape(learner.attribution)}, "
                f"{html.escape(learner.license)})</div>"
                f'<audio id="a-{c.id}" controls preload=none src="audio/{c.audio_key}.wav"></audio>'
                + _words(c.id, f"a-{c.id}", res["words"], c.target_word)
                + issues
                + f"<div class=meta>Reference: {html.escape(ref_id)}</div>"
                f'<audio id="r-{c.id}" controls preload=none src="audio/{ref_id}.wav"></audio>'
                + _words(c.id + "-ref", f"r-{c.id}", _ref_words(ref_an), None, labels=False)
                + "</div>"
            )
    sources = sorted({(r.attribution, r.license, r.source_url) for r in rec_by_id.values()})
    parts.append("<h2>Sources</h2><ul>")
    parts += [
        f'<li>{html.escape(a)} — {html.escape(lic)} — <a href="{html.escape(u)}">{html.escape(u)}</a></li>'
        for a, lic, u in sources
    ]
    parts.append(f"</ul></main><script>{_JS}</script></body></html>")
    path.write_text("".join(parts), "utf-8")
    (path.parent / "labels_schema.json").write_text(
        json.dumps({"case": "str", "word_index": "int", "word": "str", "ok": "bool"}), "utf-8"
    )

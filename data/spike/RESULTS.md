# Milestone 0b — Sanskrit tooling spike results (2026-10-07)

Question: can deterministic, rule-based tooling produce the word split (pada)
and grammar (morphology) for our shlokas, so the LLM only writes explanations
on top? CLAUDE.md requires this.

Reproduce: `uv run python -m spike.fetch --dcs && uv run python -m spike.eval_dcs && uv run python -m spike.draft`

## Tools considered

| Tool | License | Status here |
|---|---|---|
| **Vidyut 0.4.0** (ambuda.org; Rust, Pāṇinian) | MIT | **Used.** Segmenter (`cheda`), lexicon of inflected forms (`kosha`), Pāṇini-based word generator (`prakriya`). pip wheel plus a 32 MB data bundle (GitHub release, pinned sha256) |
| sanskrit_parser | MIT | Installs, but its data comes from INRIA (gitlab.inria.fr / sanskrit.inria.fr), which is blocked from the dev sandbox. Not evaluated |
| INRIA Sanskrit Heritage | LGPL (data) | Host blocked. Strong option to evaluate later from a normal network |
| GRETIL Ṛgveda **pada-pāṭha** | CC BY-NC-SA 4.0 | **Used** as the traditional, scholarly word split for Ṛgveda mantras |
| DCS gold annotations (Hellwig) via HF mirror | CC BY 4.0 (DCS) | **Used for evaluation only** |

## Results vs DCS gold (2,000 random sentences, 12,469 words)

| Measure | Result |
|---|---|
| Sentence split exactly right (raw segmenter) | 9.7% |
| Sentence split exactly right (conservative: keep known words whole) | **20.1%** |
| Split token F1 (raw → conservative) | 0.58 → **0.68** |
| Lexicon knows the form (coverage) | **81.8%** |
| Nouns/adjectives: gold case + number among candidates | **86.6%** |
| Nouns/adjectives: our default (top-ranked) is right | 64.7% |

These are lower bounds. DCS sometimes keeps sandhi forms or splits compounds
differently from us, and 728 sampled rows with incomplete gold were skipped.

The typical failure is over-splitting: *saṃyuge* becomes sam + yuge, *sarvāḥ* becomes sa + ṛvāḥ.
The conservative rule fixes most of these. Under-splitting is rarer
(*gururbrahmā* written without spaces stays whole).

## Our shlokas (drafts in `spike/out/drafts/*.yaml`)

| Shloka | Split from | Padas | Unknown to lexicon | Notes |
|---|---|---|---|---|
| Gayatri (RV 3.62.10) | pada-pāṭha | 10 | 3 (*dhīmahi*, *dhiyaḥ*, *pracodayāt*) | Vedic verb forms not in the classical lexicon |
| Mahāmṛtyuñjaya (RV 7.59.12) | pada-pāṭha | 11 | 0 | `urvārukam-iva` correctly becomes two padas |
| BG 2.47 | Vidyut (conservative) | 16 | 0 | Split correct after avagraha handling (*saṅgo 'stv* → saṅgaḥ astu) |

Examples of wrong defaults (the right reading is usually in the list, but not first):
*savituḥ* defaults to ablative (should be genitive); *bhūr* defaults to an
indeclinable (should be a verb form of √bhū after *mā*); *te* defaults to
"tā nom. dual" (should be the pronoun for "your/to you").

**A lexicon error was found:** for *lakṣmīḥ*, Vidyut only knows the accusative plural.
It treats the stem like *nadī*, so it has no nominative singular. This is
exactly why advisor verification is mandatory.

## Conclusions → decisions

1. **Rule-based tooling proposes; the advisor decides.** Accuracy is far too low
   for unreviewed use (20% of sentences split exactly right; 65% top-1 for
   nouns). It is good enough to save advisor time: 87% of noun readings can
   be picked from a list rather than typed.
2. **Splits come from a pada-pāṭha when the corpus has one** (Vedic mantras).
   Otherwise Vidyut proposes a conservative split for the advisor to check.
   `split_source` records which, for `content_audit`.
3. **The console needs grouped, searchable candidates.** Common words have up to
   76 lexicon readings (*te*), and many differ only in gender. It must also allow free-entry
   analysis for unknown (Vedic) forms.
4. **Vedic coverage is the gap.** 3 of 10 Gayatri padas are unknown. Before
   Milestone 1, evaluate INRIA Heritage (Vedic support) from a normal network.
   Otherwise the advisor enters these by hand: about 10–20 words across the 10 shlokas.
5. **Licensing:** the RV pada-pāṭha is non-commercial, same as the Saṃhitā text
   (already flagged in `data/sources.yaml`).
6. **Vidyut becomes a production dependency of the content pipeline**: MIT,
   offline only, never in the learner request path. **Needs product-owner
   approval** as a new major dependency (CLAUDE.md rule).

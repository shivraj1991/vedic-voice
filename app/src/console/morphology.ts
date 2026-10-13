/**
 * Review logic for word analyses.
 *
 * The rule-based pipeline proposes readings (`proposed`) and lists every
 * lexicon reading as `candidates` (up to ~76 for common words). The advisor picks
 * one or enters their own; the pick is stored as `morphology.chosen`, which the
 * learner view prefers over `proposed`. Grammar is never invented here: the
 * console only selects among rule-based candidates or records the advisor's entry.
 */
import type { Analysis, AnalysisEdit, Morphology, Reading } from '@/api/types';

/** The reading learners see: the advisor's choice, else the pipeline proposal. */
export function currentReading(m: Morphology): Reading | null {
  return m.chosen ?? m.proposed ?? null;
}

export function sameReading(a: Reading | null | undefined, b: Reading | null | undefined): boolean {
  if (!a || !b) return false;
  return a.kind === b.kind && a.lemma === b.lemma && a.label === b.label;
}

/** Lowercase and strip diacritics, so "dhimahi" finds "dhīmahi" and "rn" finds "ṛṇ". */
export function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
}

function haystack(r: Reading): string {
  return fold(
    [r.label, r.lemma, r.root, r.case, r.number, r.gender, r.person, r.tense_mood, r.voice, r.kind]
      .filter(Boolean)
      .join(' '),
  );
}

export interface CandidateGroup {
  lemma: string;
  readings: Reading[];
}

/**
 * Candidates grouped by lemma, filtered by a search query (every word must match).
 * The proposed reading's lemma comes first; other groups keep pipeline order.
 */
export function groupCandidates(m: Morphology, query = ''): CandidateGroup[] {
  const terms = fold(query).split(/\s+/).filter(Boolean);
  const groups = new Map<string, Reading[]>();
  for (const r of m.candidates ?? []) {
    const text = haystack(r);
    if (!terms.every((t) => text.includes(t))) continue;
    const key = r.lemma ?? '(no lemma)';
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  const first = m.proposed?.lemma ?? undefined;
  return [...groups.entries()]
    .map(([lemma, readings]) => ({ lemma, readings }))
    .sort((a, b) => Number(b.lemma === first) - Number(a.lemma === first));
}

/** A reading the advisor typed in (e.g. Vedic forms unknown to the lexicon). */
export function manualReading(lemma: string, label: string): Reading {
  return { kind: 'manual', lemma: lemma.trim() || null, label: label.trim() };
}

/** New morphology with `reading` as the advisor's choice; pipeline data kept for provenance. */
export function withChoice(m: Morphology, reading: Reading | null): Morphology {
  const next: Morphology = { ...m };
  if (reading) next.chosen = reading;
  else delete next.chosen;
  return next;
}

/** The edit the API needs for the reviewer's draft (only changed fields). */
export function analysisChanges(
  a: Analysis,
  chosen: Reading | null,
  meaning: string,
  explanation: string,
): AnalysisEdit {
  const out: AnalysisEdit = {};
  if (!sameReading(chosen, a.morphology.chosen ?? null) && chosen) {
    out.morphology = withChoice(a.morphology, chosen);
    if (chosen.lemma && chosen.lemma !== a.lemma) out.lemma = chosen.lemma;
  }
  if (meaning !== (a.meaning ?? '')) out.meaning = meaning;
  if (explanation !== (a.explanation ?? '')) out.explanation = explanation;
  return out;
}

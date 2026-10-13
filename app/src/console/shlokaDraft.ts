/** Editing a shloka's text: the form draft and the minimal change set sent to the API. */
import type { ShlokaDetail, ShlokaEdit } from '@/api/types';

export const TEXT_FIELDS = ['title', 'devanagari', 'iast', 'translation', 'source_ref'] as const;
export type Draft = Record<(typeof TEXT_FIELDS)[number] | 'review_notes', string>;

export function draftOf(s: ShlokaDetail): Draft {
  return {
    title: s.title,
    devanagari: s.devanagari,
    iast: s.iast,
    translation: s.translation ?? '',
    source_ref: s.source_ref ?? '',
    review_notes: s.review_notes ?? '',
  };
}

/** Only the fields that changed (the API audits exactly what is sent). */
export function changedFields(s: ShlokaDetail, d: Draft): ShlokaEdit {
  const before = draftOf(s);
  const out: ShlokaEdit = {};
  for (const k of Object.keys(d) as (keyof Draft)[]) {
    if (d[k] !== before[k]) out[k] = d[k];
  }
  return out;
}

/** Text edits on a verified shloka send it back to review; review notes do not. */
export function resetsReview(s: ShlokaDetail, changes: ShlokaEdit): boolean {
  return s.verified && Object.keys(changes).some((k) => k !== 'review_notes');
}

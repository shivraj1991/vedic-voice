/**
 * Pronunciation issue codes for advisor word labels.
 *
 * Same vocabulary as the scorer (scoring/src/vv_scoring/phonology.py and scorer.py),
 * so advisor labels can be compared with what the scorer reports.
 */
export const ISSUE_CODES: { code: string; label: string }[] = [
  { code: 'aspiration_missing', label: 'Missing breath (kh, gh, th, dh, bh…)' },
  { code: 'aspiration_extra', label: 'Extra breath' },
  { code: 'retroflex_missing', label: 'Retroflex said as dental (ṭ ḍ ṇ ṣ)' },
  { code: 'retroflex_extra', label: 'Dental said as retroflex' },
  { code: 'vowel_length_short', label: 'Long vowel said short' },
  { code: 'vowel_length_long', label: 'Short vowel said long' },
  { code: 'vowel_quality', label: 'Wrong vowel' },
  { code: 'nasal', label: 'Nasal (ṃ, ṅ, ñ, ṇ, n, m)' },
  { code: 'sibilant', label: 'Sibilant (ś, ṣ, s)' },
  { code: 'visarga_missing', label: 'Visarga (ḥ) not heard' },
  { code: 'sound_changed', label: 'Other sound changed' },
  { code: 'sound_missing', label: 'Sound dropped' },
  { code: 'word_missing', label: 'Word missing' },
  { code: 'unclear', label: 'Unclear' },
];

export function issueLabel(code: string | null | undefined): string {
  if (!code) return '';
  return ISSUE_CODES.find((i) => i.code === code)?.label ?? code;
}

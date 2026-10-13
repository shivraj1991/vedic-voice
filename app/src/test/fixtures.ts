/** Test data shaped like the API's responses (two words of the Gāyatrī). */
import type { Analysis, AudioAssetDetail, Reading, ShlokaDetail, ShlokaSummary } from '@/api/types';

export const reading = (lemma: string, label: string, extra: Partial<Reading> = {}): Reading => ({
  kind: 'subanta',
  lemma,
  label,
  ...extra,
});

export const TAT_NOM = reading('tad', 'tad (n.) nominative singular', { case: 'nominative' });
export const TAT_ACC = reading('tad', 'tad (n.) accusative singular', { case: 'accusative' });
export const TA_GEN = reading('ta', 'ta (m.) genitive singular', { case: 'genitive' });

export function analysis(over: Partial<Analysis> = {}): Analysis {
  return {
    id: 'a-tat',
    position: 0,
    pada_iast: 'tat',
    lemma: 'tad',
    morphology: {
      split_source: 'padapatha',
      status: 'ambiguous',
      proposed: TAT_NOM,
      candidates: [TA_GEN, TAT_NOM, TAT_ACC],
    },
    meaning: null,
    explanation: null,
    analysis_tool: 'vidyut',
    verified: false,
    verified_by: null,
    ...over,
  };
}

export function shloka(over: Partial<ShlokaDetail> = {}): ShlokaDetail {
  return {
    slug: 'gayatri',
    title: 'Gāyatrī Mantra',
    devanagari: 'तत् सवितुर्',
    iast: 'tat savitur',
    translation: null,
    source_ref: 'RV 3.62.10',
    source: { key: 'gretil', name: 'GRETIL Ṛgveda', license: 'CC BY-NC-SA 4.0', url: null },
    verified: false,
    verified_by: null,
    verified_at: null,
    review_notes: 'Ṛgveda text only.',
    updated_at: '2026-10-07T13:06:00Z',
    words: [
      {
        id: 'w0',
        position: 0,
        surface_iast: 'tat',
        surface_devanagari: 'तत्',
        analyses: [analysis()],
      },
      {
        id: 'w1',
        position: 1,
        surface_iast: 'savitur',
        surface_devanagari: 'सवितुर्',
        analyses: [
          analysis({
            id: 'a-savitur',
            pada_iast: 'savituḥ',
            lemma: 'savitṛ',
            morphology: {
              proposed: reading('savitṛ', 'savitṛ (m.) genitive singular'),
              candidates: [],
            },
            meaning: 'of Savitṛ',
            verified: true,
            verified_by: 'user_advisor',
          }),
        ],
      },
    ],
    ...over,
  };
}

export const SUMMARY: ShlokaSummary = {
  slug: 'gayatri',
  title: 'Gāyatrī Mantra',
  verified: false,
  verified_at: null,
  updated_at: '2026-10-07T13:06:00Z',
  analyses: 2,
  analyses_verified: 1,
};

export function recording(over: Partial<AudioAssetDetail> = {}): AudioAssetDetail {
  return {
    id: 'rec-1',
    shloka_id: 's-1',
    shloka_slug: 'gayatri',
    shloka_title: 'Gāyatrī Mantra',
    kind: 'reference',
    r2_key: 'ref/gayatri/0123456789abcdef0123456789abcdef.m4a',
    license: 'owned',
    attribution: 'Vedic Voice',
    reciter: 'Advisor A',
    source_url: null,
    duration_ms: 12000,
    verified: false,
    is_active_reference: false,
    created_at: '2026-10-08T10:00:00Z',
    words: shloka().words.map(({ analyses: _, ...w }) => w),
    labels: [],
    ...over,
  };
}

/**
 * Response shapes of the Vedic Voice API (backend/src/vv_backend/api/routes_*.py).
 * Kept by hand: the API is small and the backend is the source of truth.
 */

export type Role = 'learner' | 'admin' | 'advisor';

export interface Me {
  id: string;
  role: Role;
  recording_consent: boolean;
  consent_version: string | null;
  timezone: string | null;
}

export interface ShlokaSummary {
  slug: string;
  title: string;
  verified: boolean;
  verified_at: string | null;
  updated_at: string;
  analyses: number;
  analyses_verified: number;
}

/** One grammatical reading from the rule-based pipeline (data/src/vv_content/analysis.py). */
export interface Reading {
  kind: string;
  lemma: string | null;
  root?: string | null;
  derivation?: string | null;
  case?: string | null;
  number?: string | null;
  gender?: string | null;
  person?: string | null;
  tense_mood?: string | null;
  voice?: string | null;
  label: string;
}

/** `word_analyses.morphology`: pipeline proposals plus the reviewer's `chosen` reading. */
export interface Morphology {
  split_source?: string;
  members?: string[];
  status?: string;
  proposed?: Reading | null;
  candidates?: Reading[];
  chosen?: Reading | null;
  [key: string]: unknown;
}

export interface Analysis {
  id: string;
  position: number;
  pada_iast: string;
  lemma: string | null;
  morphology: Morphology;
  meaning: string | null;
  explanation: string | null;
  analysis_tool: string | null;
  verified: boolean;
  verified_by: string | null;
}

export interface Word {
  id: string;
  position: number;
  surface_iast: string;
  surface_devanagari: string;
  analyses: Analysis[];
}

export interface ShlokaDetail {
  slug: string;
  title: string;
  devanagari: string;
  iast: string;
  translation: string | null;
  source_ref: string | null;
  source: { key: string; name: string; license: string; url: string | null };
  verified: boolean;
  verified_by: string | null;
  verified_at: string | null;
  review_notes: string | null;
  updated_at: string;
  words: Word[];
}

export type ShlokaEdit = Partial<
  Pick<
    ShlokaDetail,
    'title' | 'devanagari' | 'iast' | 'translation' | 'source_ref' | 'review_notes'
  >
>;

export type AnalysisEdit = Partial<
  Pick<Analysis, 'pada_iast' | 'lemma' | 'meaning' | 'explanation' | 'morphology'>
>;

export interface AuditEntry {
  id: number;
  actor: string;
  entity: string;
  entity_id: string;
  action: string;
  diff: Record<string, unknown>;
  at: string;
}

export type AssetKind = 'reference' | 'test';

export interface AudioAsset {
  id: string;
  shloka_id: string;
  shloka_slug: string;
  shloka_title: string;
  kind: AssetKind | 'user_consented';
  r2_key: string;
  license: string | null;
  attribution: string | null;
  reciter: string | null;
  source_url: string | null;
  duration_ms: number | null;
  verified: boolean;
  is_active_reference: boolean;
  created_at: string;
}

export interface WordLabel {
  shloka_word_id: string;
  ok: boolean;
  issue_code: string | null;
  note: string | null;
}

export interface AudioAssetDetail extends AudioAsset {
  words: Omit<Word, 'analyses'>[];
  labels: WordLabel[];
}

export interface SignedUpload {
  url: string;
  method: string;
  headers: Record<string, string>;
  r2_key: string;
  expires_in: number;
}

export interface AssetRegistration {
  shloka_slug: string;
  kind: AssetKind;
  r2_key: string;
  source_url?: string;
  license?: string;
  attribution?: string;
  reciter?: string;
  duration_ms?: number;
}

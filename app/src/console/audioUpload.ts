/**
 * Uploading a reference/test recording: audio goes straight to R2 through a
 * short-lived signed URL (never through the API), then the API registers it.
 */
import type { Api } from '@/api/client';
import type { AssetKind, AssetRegistration, AudioAsset } from '@/api/types';

/** Content types the API accepts for console uploads (AssetUploadUrlIn). */
const BY_EXTENSION: Record<string, string> = {
  m4a: 'audio/mp4',
  mp4: 'audio/mp4',
  aac: 'audio/aac',
  ogg: 'audio/ogg',
  wav: 'audio/wav',
  flac: 'audio/flac',
};
const ACCEPTED = new Set([...Object.values(BY_EXTENSION), 'audio/m4a', 'audio/x-m4a']);

/** The upload content type for a picked file, or null if the API won't accept it. */
export function audioContentType(name: string, mimeType?: string | null): string | null {
  if (mimeType && ACCEPTED.has(mimeType)) return mimeType;
  if (mimeType === 'audio/x-wav' || mimeType === 'audio/wave') return 'audio/wav';
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  return BY_EXTENSION[ext] ?? null;
}

export interface PickedAudio {
  name: string;
  uri: string;
  mimeType?: string | null;
  /** Browser File (web); on native the file is read from `uri`. */
  file?: Blob;
}

export type RecordingMeta = Omit<AssetRegistration, 'shloka_slug' | 'kind' | 'r2_key'>;

export async function uploadRecording(
  api: Api,
  shlokaSlug: string,
  kind: AssetKind,
  audio: PickedAudio,
  meta: RecordingMeta,
  fetchImpl: typeof fetch = fetch,
): Promise<AudioAsset> {
  const contentType = audioContentType(audio.name, audio.mimeType);
  if (!contentType) throw new Error('Unsupported audio format. Use m4a, aac, ogg, wav or flac.');
  if (kind === 'test' && !(meta.license && meta.attribution)) {
    throw new Error('Test recordings need a license and an attribution.');
  }
  const signed = await api.assetUploadUrl(shlokaSlug, kind, contentType);
  const body = audio.file ?? (await (await fetchImpl(audio.uri)).blob());
  const put = await fetchImpl(signed.url, { method: signed.method, headers: signed.headers, body });
  if (!put.ok) throw new Error(`Upload to storage failed (${put.status}).`);
  const clean = Object.fromEntries(
    Object.entries(meta).filter(([, v]) => v !== undefined && v !== ''),
  ) as RecordingMeta;
  return api.registerAudio({ shloka_slug: shlokaSlug, kind, r2_key: signed.r2_key, ...clean });
}

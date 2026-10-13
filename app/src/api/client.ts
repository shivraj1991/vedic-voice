/**
 * Typed client for the Vedic Voice API.
 *
 * Every request carries the current session token (Clerk, or a simulated dev
 * token). Roles are never sent: the server reads them from the verified token.
 * `fetchImpl` is injectable so tests run without a network.
 */
import type {
  AnalysisEdit,
  AssetKind,
  AssetRegistration,
  AudioAsset,
  AudioAssetDetail,
  AuditEntry,
  Me,
  ShlokaDetail,
  ShlokaEdit,
  ShlokaSummary,
  SignedUpload,
  WordLabel,
} from './types';

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

type ValidationItem = { loc?: (string | number)[]; msg?: string };

/** FastAPI errors: `detail` is a string, or a list of validation items. */
export function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationItem[])
      .map((d) => [d.loc?.filter((p) => p !== 'body').join('.'), d.msg].filter(Boolean).join(': '))
      .join('; ');
  }
  return `request failed (${status})`;
}

/** Plain-language messages for errors the console shows often. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'Your session has expired. Please sign in again.';
    if (error.status === 403) return 'Your role does not allow this action.';
    if (error.status === 503) return `Not available on this server yet: ${error.message}.`;
    return error.message;
  }
  if (error instanceof TypeError) return 'Cannot reach the server. Check your connection.';
  return error instanceof Error ? error.message : String(error);
}

export type TokenGetter = () => Promise<string | null>;

export function createApi(baseUrl: string, getToken: TokenGetter, fetchImpl: typeof fetch = fetch) {
  const base = baseUrl.replace(/\/+$/, '');

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = await getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const res = await fetchImpl(`${base}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (res.status === 204) return undefined as T;
    const data: unknown = await res.json().catch(() => null);
    if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, data));
    return data as T;
  }

  const enc = encodeURIComponent;
  return {
    me: () => request<Me>('GET', '/me'),

    listShlokas: () => request<ShlokaSummary[]>('GET', '/admin/shlokas'),
    getShloka: (slug: string) => request<ShlokaDetail>('GET', `/admin/shlokas/${enc(slug)}`),
    editShloka: (slug: string, changes: ShlokaEdit) =>
      request<ShlokaDetail>('PATCH', `/admin/shlokas/${enc(slug)}`, changes),
    verifyShloka: (slug: string, notes?: string) =>
      request<ShlokaDetail>('POST', `/admin/shlokas/${enc(slug)}/verify`, notes ? { notes } : {}),

    editAnalysis: (id: string, changes: AnalysisEdit) =>
      request<{ id: string; verified: boolean }>(
        'PATCH',
        `/admin/word-analyses/${enc(id)}`,
        changes,
      ),
    verifyAnalysis: (id: string) =>
      request<{ id: string; verified: boolean }>('POST', `/admin/word-analyses/${enc(id)}/verify`),

    audit: (entityId?: string, limit = 100) =>
      request<AuditEntry[]>(
        'GET',
        `/admin/audit?limit=${limit}${entityId ? `&entity_id=${enc(entityId)}` : ''}`,
      ),

    listAudio: (shloka?: string) =>
      request<AudioAsset[]>('GET', `/admin/audio${shloka ? `?shloka=${enc(shloka)}` : ''}`),
    getAudio: (id: string) => request<AudioAssetDetail>('GET', `/admin/audio/${enc(id)}`),
    playUrl: (id: string) =>
      request<{ url: string; expires_in: number }>('GET', `/admin/audio/${enc(id)}/play-url`),
    assetUploadUrl: (shlokaSlug: string, kind: AssetKind, contentType: string) =>
      request<SignedUpload>('POST', '/admin/audio/upload-url', {
        shloka_slug: shlokaSlug,
        kind,
        content_type: contentType,
      }),
    registerAudio: (body: AssetRegistration) => request<AudioAsset>('POST', '/admin/audio', body),
    verifyAudio: (id: string) => request<AudioAsset>('POST', `/admin/audio/${enc(id)}/verify`),
    activateAudio: (id: string) => request<AudioAsset>('POST', `/admin/audio/${enc(id)}/activate`),
    putLabel: (assetId: string, label: WordLabel) =>
      request<void>('PUT', '/admin/word-labels', { audio_asset_id: assetId, ...label }),
  };
}

export type Api = ReturnType<typeof createApi>;

import { describeDiff } from '@/console/audit';
import { audioContentType, uploadRecording } from '@/console/audioUpload';
import { issueLabel, ISSUE_CODES } from '@/console/issues';
import { changedFields, draftOf, resetsReview } from '@/console/shlokaDraft';
import type { Api } from '@/api/client';
import { shloka } from '@/test/fixtures';

describe('shloka drafts', () => {
  it('sends only changed fields', () => {
    const s = shloka();
    expect(changedFields(s, draftOf(s))).toEqual({});
    expect(changedFields(s, { ...draftOf(s), translation: 'That…' })).toEqual({
      translation: 'That…',
    });
  });

  it('warns that text edits, but not review notes, send a verified shloka back', () => {
    const s = shloka({ verified: true });
    expect(resetsReview(s, { review_notes: 'checked' })).toBe(false);
    expect(resetsReview(s, { iast: 'tat savituḥ' })).toBe(true);
    expect(resetsReview(shloka(), { iast: 'x' })).toBe(false);
  });
});

describe('audit lines', () => {
  it('shows before → after and shortens long values', () => {
    expect(describeDiff({ verified: [true, false], shloka: 'gayatri' })).toEqual([
      'verified: true → false',
      'shloka: gayatri',
    ]);
    expect(describeDiff({ notes: 'x'.repeat(200) })[0]).toHaveLength('notes: '.length + 78);
  });

  it('summarises morphology changes as the chosen reading', () => {
    const before = { proposed: { label: 'a' }, candidates: [] };
    const after = { ...before, chosen: { label: 'tad (n.) nominative singular' } };
    expect(describeDiff({ morphology: [before, after] })).toEqual([
      'reading: (not chosen) → tad (n.) nominative singular',
    ]);
  });
});

describe('issue codes', () => {
  it('are unique and labelled', () => {
    const codes = ISSUE_CODES.map((i) => i.code);
    expect(new Set(codes).size).toBe(codes.length);
    expect(issueLabel('visarga_missing')).toMatch(/Visarga/);
    expect(issueLabel('something_new')).toBe('something_new');
  });
});

describe('recording upload', () => {
  it('accepts the formats the API accepts', () => {
    expect(audioContentType('a.m4a')).toBe('audio/mp4');
    expect(audioContentType('a.WAV', 'audio/x-wav')).toBe('audio/wav');
    expect(audioContentType('a.bin', 'audio/ogg')).toBe('audio/ogg');
    expect(audioContentType('a.mp3', 'audio/mpeg')).toBeNull();
  });

  function fakeApi() {
    return {
      assetUploadUrl: jest.fn().mockResolvedValue({
        url: 'https://r2.example/put',
        method: 'PUT',
        headers: { 'Content-Type': 'audio/mp4' },
        r2_key: 'ref/gayatri/k.m4a',
        expires_in: 600,
      }),
      registerAudio: jest.fn().mockResolvedValue({ id: 'new' }),
    };
  }

  it('uploads straight to storage, then registers without empty fields', async () => {
    const api = fakeApi();
    const file = new Blob(['x']);
    const fetchImpl = jest.fn().mockResolvedValue({ ok: true, status: 200 });
    await uploadRecording(
      api as unknown as Api,
      'gayatri',
      'reference',
      { name: 'take1.m4a', uri: 'blob:1', file },
      { reciter: 'A', license: '', attribution: undefined },
      fetchImpl,
    );
    expect(api.assetUploadUrl).toHaveBeenCalledWith('gayatri', 'reference', 'audio/mp4');
    expect(fetchImpl).toHaveBeenCalledWith('https://r2.example/put', {
      method: 'PUT',
      headers: { 'Content-Type': 'audio/mp4' },
      body: file,
    });
    expect(api.registerAudio).toHaveBeenCalledWith({
      shloka_slug: 'gayatri',
      kind: 'reference',
      r2_key: 'ref/gayatri/k.m4a',
      reciter: 'A',
    });
  });

  it('refuses test recordings without license and attribution, before uploading', async () => {
    const api = fakeApi();
    await expect(
      uploadRecording(api as unknown as Api, 'gayatri', 'test', { name: 'a.ogg', uri: 'x' }, {}),
    ).rejects.toThrow(/license/);
    expect(api.assetUploadUrl).not.toHaveBeenCalled();
  });

  it('does not register when the storage upload fails', async () => {
    const api = fakeApi();
    const fetchImpl = jest.fn().mockResolvedValue({ ok: false, status: 403 });
    await expect(
      uploadRecording(
        api as unknown as Api,
        'gayatri',
        'reference',
        { name: 'a.m4a', uri: 'x', file: new Blob(['x']) },
        {},
        fetchImpl,
      ),
    ).rejects.toThrow(/403/);
    expect(api.registerAudio).not.toHaveBeenCalled();
  });
});

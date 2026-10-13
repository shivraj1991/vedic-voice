import { ApiError, createApi, describeError, errorMessage } from '@/api/client';

function response(status: number, body?: unknown) {
  return {
    ok: status < 400,
    status,
    json: () => (body === undefined ? Promise.reject(new Error('no body')) : Promise.resolve(body)),
  } as Response;
}

describe('createApi', () => {
  it('sends the session token and JSON bodies', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(response(200, { slug: 'gayatri' }));
    const api = createApi('https://api.example/', async () => 'tok', fetchImpl);
    await api.editShloka('gayatri', { translation: 'That…' });
    expect(fetchImpl).toHaveBeenCalledWith('https://api.example/admin/shlokas/gayatri', {
      method: 'PATCH',
      headers: { Authorization: 'Bearer tok', 'Content-Type': 'application/json' },
      body: '{"translation":"That…"}',
    });
  });

  it('never sends a role, and sends no auth header when signed out', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(response(200, {}));
    const api = createApi('https://api.example', async () => null, fetchImpl);
    await api.verifyShloka('gayatri');
    const [, init] = fetchImpl.mock.calls[0];
    expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
    expect(init.body).toBe('{}');
  });

  it('encodes path and query parameters', async () => {
    const fetchImpl = jest.fn().mockResolvedValue(response(200, []));
    const api = createApi('https://api.example', async () => 't', fetchImpl);
    await api.listAudio('a/b');
    await api.audit('id 1', 5);
    expect(fetchImpl.mock.calls.map((c) => c[0])).toEqual([
      'https://api.example/admin/audio?shloka=a%2Fb',
      'https://api.example/admin/audit?limit=5&entity_id=id%201',
    ]);
  });

  it('handles 204 and raises ApiError with the server detail', async () => {
    const ok = createApi('https://x', async () => 't', jest.fn().mockResolvedValue(response(204)));
    await expect(
      ok.putLabel('r', { shloka_word_id: 'w', ok: true, issue_code: null, note: null }),
    ).resolves.toBeUndefined();

    const bad = createApi(
      'https://x',
      async () => 't',
      jest.fn().mockResolvedValue(response(403, { detail: 'insufficient role' })),
    );
    await expect(bad.verifyAnalysis('a')).rejects.toEqual(new ApiError(403, 'insufficient role'));
  });
});

describe('error messages', () => {
  it('reads FastAPI validation details', () => {
    const body = {
      detail: [{ loc: ['body', 'title'], msg: 'String should have at most 200 characters' }],
    };
    expect(errorMessage(422, body)).toBe('title: String should have at most 200 characters');
    expect(errorMessage(500, null)).toBe('request failed (500)');
  });

  it('explains common failures in plain language', () => {
    expect(describeError(new ApiError(403, 'insufficient role'))).toMatch(/role does not allow/);
    expect(describeError(new ApiError(503, 'audio storage not configured'))).toMatch(
      /Not available on this server yet: audio storage/,
    );
    expect(describeError(new TypeError('Network request failed'))).toMatch(/Cannot reach/);
  });
});

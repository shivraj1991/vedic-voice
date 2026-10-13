import { resolveAuthMode } from '@/auth/config';

describe('resolveAuthMode', () => {
  const key = 'pk_test_ZXhjaXRpbmctbWFuLTQzMzEuY2xlcmsuYWNjb3VudHMuZGV2JA';

  it('uses Clerk whenever a publishable key is set', () => {
    expect(resolveAuthMode({ clerkPublishableKey: key, devAuth: '1', isDevBuild: true })).toEqual({
      kind: 'clerk',
      publishableKey: key,
    });
  });

  it('rejects something that is not a publishable key (e.g. a secret key)', () => {
    expect(resolveAuthMode({ clerkPublishableKey: 'sk_test_x', isDevBuild: true }).kind).toBe(
      'missing',
    );
  });

  it('allows simulated-token sign-in only in development builds, when enabled', () => {
    expect(resolveAuthMode({ devAuth: '1', isDevBuild: true })).toEqual({ kind: 'dev' });
    expect(resolveAuthMode({ devAuth: '1', isDevBuild: false }).kind).toBe('missing');
    expect(resolveAuthMode({ isDevBuild: true }).kind).toBe('missing');
  });
});

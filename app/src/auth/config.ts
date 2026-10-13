/**
 * Which sign-in the app uses, decided once from build-time configuration.
 *
 * - `clerk`: real sign-in (Clerk). The default whenever a publishable key is set.
 * - `dev`: paste a simulated token from `vv_backend.devtools`, for local development
 *   before/without Clerk. Only in development builds and only when explicitly enabled;
 *   the backend refuses simulated tokens when VV_ENV=prod anyway.
 * - `missing`: nothing configured; the app shows a setup message instead of failing.
 */
export type AuthMode =
  { kind: 'clerk'; publishableKey: string } | { kind: 'dev' } | { kind: 'missing'; reason: string };

export interface AuthEnv {
  clerkPublishableKey?: string;
  devAuth?: string;
  isDevBuild: boolean;
}

export function resolveAuthMode(env: AuthEnv): AuthMode {
  const key = env.clerkPublishableKey?.trim();
  if (key) {
    if (!/^pk_(test|live)_/.test(key)) {
      return { kind: 'missing', reason: 'EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY is not a Clerk key.' };
    }
    return { kind: 'clerk', publishableKey: key };
  }
  if (env.isDevBuild && env.devAuth === '1') return { kind: 'dev' };
  return {
    kind: 'missing',
    reason: 'Set EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY (see app/.env.example).',
  };
}

/** Reads the environment. Expo inlines EXPO_PUBLIC_* only for direct `process.env.X` access. */
export function authModeFromEnv(): AuthMode {
  return resolveAuthMode({
    clerkPublishableKey: process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY,
    devAuth: process.env.EXPO_PUBLIC_DEV_AUTH,
    isDevBuild: __DEV__,
  });
}

export function apiUrlFromEnv(): string | null {
  return process.env.EXPO_PUBLIC_API_URL?.trim() || null;
}

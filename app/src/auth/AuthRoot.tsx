/**
 * Provides the session for the configured auth mode (see config.ts).
 *
 * Clerk tokens are cached with expo-secure-store on native (encrypted); Clerk's
 * web SDK manages its own cookies. Simulated dev tokens are kept in memory only.
 */
import { ClerkProvider, useAuth } from '@clerk/expo';
import { tokenCache } from '@clerk/expo/token-cache';
import { type ReactNode, useLayoutEffect, useMemo, useRef, useState } from 'react';

import type { AuthMode } from './config';
import { type Session, SessionContext } from './session';

function ClerkSession({ children }: { children: ReactNode }) {
  const auth = useAuth();
  // Clerk's functions may change identity between renders; screens must not refetch then.
  const latest = useRef(auth);
  useLayoutEffect(() => {
    latest.current = auth;
  });
  const status = !auth.isLoaded ? 'loading' : auth.isSignedIn ? 'signedIn' : 'signedOut';
  const session = useMemo<Session>(
    () => ({
      status,
      mode: 'clerk',
      getToken: () => latest.current.getToken(),
      signOut: () => latest.current.signOut(),
    }),
    [status],
  );
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

function DevSession({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const session = useMemo<Session>(
    () => ({
      status: token ? 'signedIn' : 'signedOut',
      mode: 'dev',
      getToken: async () => token,
      signOut: async () => setToken(null),
      signInWithToken: (t: string) => setToken(t.trim() || null),
    }),
    [token],
  );
  return <SessionContext.Provider value={session}>{children}</SessionContext.Provider>;
}

export function AuthRoot({ mode, children }: { mode: AuthMode; children: ReactNode }) {
  if (mode.kind === 'clerk') {
    return (
      <ClerkProvider publishableKey={mode.publishableKey} tokenCache={tokenCache}>
        <ClerkSession>{children}</ClerkSession>
      </ClerkProvider>
    );
  }
  if (mode.kind === 'dev') return <DevSession>{children}</DevSession>;
  return null;
}

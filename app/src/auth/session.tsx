/**
 * The app's view of the signed-in session, independent of how sign-in happened
 * (Clerk or a simulated dev token). Screens only use `useSession()`.
 */
import { createContext, useContext } from 'react';

export type SessionStatus = 'loading' | 'signedOut' | 'signedIn';

export interface Session {
  status: SessionStatus;
  mode: 'clerk' | 'dev';
  getToken: () => Promise<string | null>;
  signOut: () => Promise<void>;
  /** Dev mode only: sign in with a pasted simulated token. */
  signInWithToken?: (token: string) => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside <AuthRoot>');
  return session;
}

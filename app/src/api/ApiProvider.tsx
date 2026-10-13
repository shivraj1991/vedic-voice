/**
 * Makes the API client and the signed-in user (`/me`) available to screens.
 *
 * The role shown and used for gating comes from `/me`, i.e. from the token the
 * server verified, not from anything stored on the device. The server enforces
 * roles on every route regardless; the console only hides what would be refused.
 */
import { createContext, type ReactNode, useContext, useMemo } from 'react';

import { useSession } from '@/auth/session';

import { type Api, createApi } from './client';
import type { Me, Role } from './types';
import { type Resource, useResource } from './useResource';

interface ApiContextValue {
  api: Api;
  me: Resource<Me>;
}

const ApiContext = createContext<ApiContextValue | null>(null);

export function ApiProvider({
  baseUrl,
  children,
  fetchImpl,
}: {
  baseUrl: string;
  children: ReactNode;
  fetchImpl?: typeof fetch;
}) {
  const session = useSession();
  const api = useMemo(
    () => createApi(baseUrl, session.getToken, fetchImpl),
    [baseUrl, session.getToken, fetchImpl],
  );
  const signedIn = session.status === 'signedIn';
  const me = useResource(() => (signedIn ? api.me() : Promise.resolve(null)), [api, signedIn]);
  const value = useMemo(() => ({ api, me: me as Resource<Me> }), [api, me]);
  return <ApiContext.Provider value={value}>{children}</ApiContext.Provider>;
}

function useApiContext(): ApiContextValue {
  const ctx = useContext(ApiContext);
  if (!ctx) throw new Error('useApi must be used inside <ApiProvider>');
  return ctx;
}

export const useApi = (): Api => useApiContext().api;
export const useMe = (): Resource<Me> => useApiContext().me;

export const isStaff = (role: Role | undefined): boolean => role === 'admin' || role === 'advisor';
export const isAdvisor = (role: Role | undefined): boolean => role === 'advisor';

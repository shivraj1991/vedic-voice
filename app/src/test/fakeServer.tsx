/**
 * A fake Vedic Voice API behind the app's injectable `fetch`, plus the providers
 * screens need. Records every call so tests can assert what was sent.
 */
import type { ReactNode } from 'react';

import { ApiProvider } from '@/api/ApiProvider';
import type { Role } from '@/api/types';
import { type Session, SessionContext } from '@/auth/session';

export const API = 'https://api.test';

type Handler = (body: unknown) => unknown;
export interface Call {
  method: string;
  path: string;
  body: unknown;
}

function json(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body } as Response;
}

export function fakeServer(role: Role, routes: Record<string, Handler | unknown>) {
  const calls: Call[] = [];
  const fetchImpl = jest.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url).replace(API, '');
    const method = init?.method ?? 'GET';
    const body = typeof init?.body === 'string' ? JSON.parse(init.body) : undefined;
    calls.push({ method, path, body });
    if (method === 'GET' && path === '/me') {
      return json(200, {
        id: 'u1',
        role,
        recording_consent: false,
        consent_version: null,
        timezone: null,
      });
    }
    const key = `${method} ${path}`;
    if (!(key in routes)) return json(404, { detail: 'not found' });
    const route = routes[key];
    const out = typeof route === 'function' ? (route as Handler)(body) : route;
    return out === undefined ? json(204, undefined) : json(200, out);
  }) as unknown as typeof fetch;

  const session: Session = {
    status: 'signedIn',
    mode: 'dev',
    getToken: async () => 'token',
    signOut: async () => {},
  };
  function Providers({ children }: { children: ReactNode }) {
    return (
      <SessionContext.Provider value={session}>
        <ApiProvider baseUrl={API} fetchImpl={fetchImpl}>
          {children}
        </ApiProvider>
      </SessionContext.Provider>
    );
  }
  const sent = (method: string, path: string) =>
    calls.filter((c) => c.method === method && c.path === path);
  return { calls, sent, Providers };
}

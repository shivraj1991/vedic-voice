/** Load data for a screen, with loading/error state and a reload function. */
import {
  type DependencyList,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

export interface Resource<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
  /** Replace the data locally (e.g. with the server's response after an edit). */
  setData: (data: T) => void;
}

function sameDeps(a: DependencyList, b: DependencyList): boolean {
  return a.length === b.length && a.every((v, i) => Object.is(v, b[i]));
}

interface State<T> {
  request: object | null;
  data: T | null;
  error: unknown;
}

/**
 * Each change of `deps` (or a reload) starts a new request; `loading` is true until
 * that request settles. Data from the previous request stays visible meanwhile.
 */
export function useResource<T>(load: () => Promise<T | null>, deps: DependencyList): Resource<T> {
  // A request is identified by object identity; new deps (compared during render, the
  // React pattern for state derived from props) or a reload start a new one.
  const [request, setRequest] = useState<{ deps: DependencyList }>(() => ({ deps }));
  if (!sameDeps(request.deps, deps)) setRequest({ deps });
  const [state, setState] = useState<State<T>>({ request: null, data: null, error: null });
  const loadRef = useRef(load);
  useLayoutEffect(() => {
    loadRef.current = load;
  });

  useEffect(() => {
    let cancelled = false;
    loadRef.current().then(
      (data) => !cancelled && setState({ request, data, error: null }),
      (error: unknown) => !cancelled && setState((s) => ({ request, data: s.data, error })),
    );
    return () => {
      cancelled = true;
    };
  }, [request]);

  const reload = useCallback(() => setRequest((r) => ({ deps: r.deps })), []);
  const setData = useCallback((data: T) => setState({ request, data, error: null }), [request]);
  const loading = state.request !== request;
  return useMemo(
    () => ({ data: state.data, error: loading ? null : state.error, loading, reload, setData }),
    [state, loading, reload, setData],
  );
}

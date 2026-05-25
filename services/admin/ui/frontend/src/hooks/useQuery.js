import { useEffect, useRef, useState, useCallback } from "react";

export function useQuery(fetcher, { interval = 0, deps = [] } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const alive = useRef(true);
  const timer = useRef(null);
  const latestFetcher = useRef(fetcher);
  latestFetcher.current = fetcher;

  const run = useCallback(async () => {
    try {
      const data = await latestFetcher.current();
      if (alive.current) setState({ data, error: null, loading: false });
    } catch (err) {
      if (alive.current) setState((s) => ({ data: s.data, error: err, loading: false }));
    }
  }, []);

  useEffect(() => {
    alive.current = true;
    setState((s) => ({ ...s, loading: true }));
    run();
    if (interval > 0) {
      timer.current = setInterval(run, interval);
    }
    return () => {
      alive.current = false;
      if (timer.current) clearInterval(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interval, ...deps]);

  return { ...state, refetch: run };
}

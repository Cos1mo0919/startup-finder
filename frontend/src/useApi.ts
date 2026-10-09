import { useEffect, useState } from "react";
export function useApi<T>(url: string, refresh = 0, adminKey = "") {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(false),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(false);
    fetch(url, { signal: controller.signal, headers: adminKey ? {"X-Admin-Key": adminKey} : {} })
      .then((r) => {
        if (!r.ok) throw Error();
        return r.json();
      })
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(true);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [url, refresh, adminKey]);
  return { data, error, loading };
}

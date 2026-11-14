import { useSearchParams } from "react-router";

import { useUpdateQuery } from "../ui/url";

// The symbol the wallet is compared with, kept in the URL (?benchmark=QQQ) so a view can be shared; without it, the
// backend's default (SPY).
const BENCHMARK_PARAM = "benchmark";

/** The chosen benchmark symbol (null for the default), and a way to change it (null or empty for the default). */
export function useBenchmarkChoice(): [string | null, (symbol: string | null) => void] {
  const [params] = useSearchParams();
  const updateQuery = useUpdateQuery();
  const symbol = params.get(BENCHMARK_PARAM);
  const choose = (next: string | null) =>
    updateQuery((current) => {
      const updated = new URLSearchParams(current);
      const cleaned = next?.trim().toUpperCase();
      if (cleaned) {
        updated.set(BENCHMARK_PARAM, cleaned);
      } else {
        updated.delete(BENCHMARK_PARAM);
      }
      return updated;
    });
  return [symbol, choose];
}

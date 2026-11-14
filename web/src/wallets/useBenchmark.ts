import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { benchmarkDaily, type BenchmarkResponse } from "../api/generated";

export type BenchmarkState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; benchmark: BenchmarkResponse };

/**
 * What the wallet's deposits would be worth in a benchmark (`symbol`, or the default when null), at the end of every day of its history. Loads on its
 * own, so a slow or failing benchmark never holds up the wallet's chart. Change `refreshKey` to load it again.
 */
export function useBenchmark(walletId: string, symbol: string | null, refreshKey = 0): BenchmarkState {
  const [state, setState] = useState<BenchmarkState>({ status: "loading" });

  useEffect(() => {
    let current = true; // ignore answers for a wallet we have moved away from
    setState({ status: "loading" });
    benchmarkDaily({ path: { wallet_id: walletId }, query: symbol ? { symbol } : undefined })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", benchmark: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [walletId, symbol, refreshKey]);

  return state;
}

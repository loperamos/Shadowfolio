import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { type PerformanceComparisonResponse, walletPerformance } from "../api/generated";

export type PerformanceState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; comparison: PerformanceComparisonResponse };

/**
 * How the wallet and its benchmark (`symbol`, or the default when null) did from `start` to `end` (YYYY-MM-DD; null
 * for its first day, or today). Loads on
 * its own, so a slow or failing comparison never holds up the page. Change `refreshKey` to load it again.
 */
export function usePerformance(
  walletId: string,
  start: string | null,
  end: string | null,
  symbol: string | null,
  refreshKey = 0,
): PerformanceState {
  const [state, setState] = useState<PerformanceState>({ status: "loading" });

  useEffect(() => {
    let current = true; // ignore answers for a period we have moved away from
    setState({ status: "loading" });
    walletPerformance({ path: { wallet_id: walletId }, query: { start, end, ...(symbol ? { symbol } : {}) } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", comparison: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [walletId, start, end, symbol, refreshKey]);

  return state;
}

import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { getWallet, type PerformanceComparisonResponse, walletPerformance, type WalletResponse } from "../api/generated";

export type ComparedWallet =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; wallet: WalletResponse; performance: PerformanceComparisonResponse };

/** A wallet whose figures have loaded, with its id. */
export type LoadedWallet = { id: string } & Extract<ComparedWallet, { status: "loaded" }>;

/**
 * Each wallet and its performance (with its daily returns) from `start` to `end` (YYYY-MM-DD; null for its first day, or
 * today), next to `symbol` (null for the default benchmark), by wallet id. Each wallet loads on its own, so a slow or
 * failing one never holds up the others.
 */
export function useComparison(walletIds: string[], start: string | null, end: string | null, symbol: string | null): Record<string, ComparedWallet> {
  const [states, setStates] = useState<Record<string, ComparedWallet>>({});
  const key = walletIds.join();

  useEffect(() => {
    let current = true; // ignore answers for a comparison we have moved away from
    const ids = key ? key.split(",") : [];
    setStates(Object.fromEntries(ids.map((id) => [id, { status: "loading" }])));
    const settle = (id: string, state: ComparedWallet) => current && setStates((all) => ({ ...all, [id]: state }));
    const query = { start, end, ...(symbol ? { symbol } : {}) };
    for (const id of ids) {
      const path = { wallet_id: id };
      Promise.all([getWallet({ path }), walletPerformance({ path, query })])
        .then(([wallet, performance]) => {
          if (wallet.data && performance.data) {
            settle(id, { status: "loaded", wallet: wallet.data, performance: performance.data });
          } else {
            settle(id, { status: "error", message: apiErrorMessage(wallet.error ?? performance.error) });
          }
        })
        .catch(() => settle(id, { status: "error", message: "Could not reach the backend." }));
    }
    return () => {
      current = false;
    };
  }, [key, start, end, symbol]);

  return states;
}

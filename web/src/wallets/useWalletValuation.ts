import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { walletValuation, type ValuationResponse } from "../api/generated";

export type ValuationState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; valuation: ValuationResponse };

/**
 * The wallet valued at the latest prices. Loads on its own, so a slow or failing valuation never blocks a page.
 * Change `refreshKey` to load it again, e.g. after the wallet's history changed.
 */
export function useWalletValuation(walletId: string, refreshKey = 0): ValuationState {
  const [state, setState] = useState<ValuationState>({ status: "loading" });

  useEffect(() => {
    let current = true; // ignore answers for a wallet we have moved away from
    setState({ status: "loading" });
    walletValuation({ path: { wallet_id: walletId } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", valuation: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [walletId, refreshKey]);

  return state;
}

/**
 * Several wallets valued at the latest prices, each loading on its own (as `useWalletValuation`), by wallet id: e.g. for
 * a list that sorts by value.
 */
export function useWalletValuations(walletIds: readonly string[]): Record<string, ValuationState> {
  const [states, setStates] = useState<Record<string, ValuationState>>({});
  const key = walletIds.join();

  useEffect(() => {
    let current = true; // ignore answers for a list we have moved away from
    const ids = key ? key.split(",") : [];
    setStates(Object.fromEntries(ids.map((id) => [id, { status: "loading" }])));
    const settle = (id: string, state: ValuationState) => current && setStates((all) => ({ ...all, [id]: state }));
    for (const id of ids) {
      walletValuation({ path: { wallet_id: id } })
        .then(({ data, error }) => settle(id, data ? { status: "loaded", valuation: data } : { status: "error", message: apiErrorMessage(error) }))
        .catch(() => settle(id, { status: "error", message: "Could not reach the backend." }));
    }
    return () => {
      current = false;
    };
  }, [key]);

  return states;
}

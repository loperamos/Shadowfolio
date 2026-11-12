import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { currentValuation, type ValuationResponse } from "../api/generated";

export type ValuationState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; valuation: ValuationResponse };

/** The wallet valued at the latest prices. Loads on its own, so a slow or failing valuation never blocks a page. */
export function useWalletValuation(walletId: string): ValuationState {
  const [state, setState] = useState<ValuationState>({ status: "loading" });

  useEffect(() => {
    let current = true; // ignore answers for a wallet we have moved away from
    setState({ status: "loading" });
    currentValuation({ path: { wallet_id: walletId } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", valuation: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [walletId]);

  return state;
}

import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { dailyValuation, type DailyValueResponse } from "../api/generated";

export type DailyValuesState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; values: DailyValueResponse[] };

/**
 * The wallet's value at the end of every day of its history. Loads on its own, so a slow or failing history never
 * blocks a page. Change `refreshKey` to load it again, e.g. after the wallet's history changed.
 */
export function useDailyValues(walletId: string, refreshKey = 0): DailyValuesState {
  const [state, setState] = useState<DailyValuesState>({ status: "loading" });

  useEffect(() => {
    let current = true; // ignore answers for a wallet we have moved away from
    setState({ status: "loading" });
    dailyValuation({ path: { wallet_id: walletId } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", values: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [walletId, refreshKey]);

  return state;
}

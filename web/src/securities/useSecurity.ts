import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { dailyCloses, type DailyCloseResponse, latestQuote, type QuoteResponse } from "../api/generated";

const NOT_FOUND_STATUS = 404;

export type QuoteState = { status: "loading" } | { status: "error"; message: string } | { status: "none" } | { status: "loaded"; quote: QuoteResponse };

/** The symbol's latest price, or "none" when market data has none. Loads on its own, so it never holds up the page. */
export function useQuote(symbol: string): QuoteState {
  const [state, setState] = useState<QuoteState>({ status: "loading" });
  useEffect(() => {
    let current = true; // ignore answers for a symbol we have moved away from
    setState({ status: "loading" });
    latestQuote({ path: { symbol } })
      .then(({ data, error, response }) => {
        if (!current) {
          return;
        }
        if (data) {
          setState({ status: "loaded", quote: data });
        } else {
          setState(response?.status === NOT_FOUND_STATUS ? { status: "none" } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [symbol]);
  return state;
}

export type ClosesState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; closes: DailyCloseResponse[] };

/** The symbol's close on each trading day from `start` to `end` (YYYY-MM-DD; null for the default history, or today). */
export function useCloses(symbol: string, start: string | null, end: string | null): ClosesState {
  const [state, setState] = useState<ClosesState>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    dailyCloses({ path: { symbol }, query: { start, end } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", closes: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [symbol, start, end]);
  return state;
}

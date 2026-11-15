import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import {
  type ArticleResponse,
  dailyCloses,
  type DailyCloseResponse,
  type FundamentalsResponse,
  latestQuote,
  type QuoteResponse,
  securityDividends,
  securityFundamentals,
  securityNews,
  securityRanges,
  type SecurityRangesResponse,
  securityStatistics,
  type SecurityStatisticsResponse,
  type DividendsResponse,
} from "../api/generated";

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

export type FundamentalsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "none" }
  | { status: "loaded"; fundamentals: FundamentalsResponse };

/** The company's reported results and ratios, or "none" when it does not report to the source (e.g. a non-US listing). */
export function useFundamentals(symbol: string): FundamentalsState {
  const [state, setState] = useState<FundamentalsState>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    securityFundamentals({ path: { symbol } })
      .then(({ data, error, response }) => {
        if (!current) {
          return;
        }
        if (data) {
          setState({ status: "loaded", fundamentals: data });
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

export type NewsState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; articles: ArticleResponse[] };

/** The latest articles about the symbol, newest first. Loads on its own, so it never holds up the page. */
export function useNews(symbol: string): NewsState {
  const [state, setState] = useState<NewsState>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    securityNews({ path: { symbol } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", articles: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [symbol]);
  return state;
}

export type RangesState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; ranges: SecurityRangesResponse };

/** Where the price and the P/E stand within their lows and highs from `start` to `end` (as for the closes). */
export function useRanges(symbol: string, start: string | null, end: string | null): RangesState {
  const [state, setState] = useState<RangesState>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    securityRanges({ path: { symbol }, query: { start, end } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", ranges: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [symbol, start, end]);
  return state;
}

export type DividendsState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; dividends: DividendsResponse };

/** The symbol's next ex-dividend date and last year's yield. Loads on its own, so it never holds up the page. */
export function useDividends(symbol: string): DividendsState {
  const [state, setState] = useState<DividendsState>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    securityDividends({ path: { symbol } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", dividends: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [symbol]);
  return state;
}

export type StatisticsState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; statistics: SecurityStatisticsResponse };

/** The trend, and over the period the volatility, deepest fall and beta. Loads on its own, so it never holds up the page. */
export function useStatistics(symbol: string, start: string | null, end: string | null): StatisticsState {
  const [state, setState] = useState<StatisticsState>({ status: "loading" });
  useEffect(() => {
    let current = true;
    setState({ status: "loading" });
    securityStatistics({ path: { symbol }, query: { start, end } })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", statistics: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [symbol, start, end]);
  return state;
}

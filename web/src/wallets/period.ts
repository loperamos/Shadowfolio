import dayjs from "dayjs";
import { useSearchParams } from "react-router";

// The period a wallet page shows (the value chart and the operations), ending today, as on most brokers' and finance
// sites' charts. It is kept in the URL (?period=1Y), so a view can be bookmarked and shared.
export enum Period {
  MONTH = "1M",
  HALF_YEAR = "6M",
  YEAR_TO_DATE = "YTD",
  YEAR = "1Y",
  ALL = "All",
}

const PERIOD_PARAM = "period";
const DAY_FORMAT = "YYYY-MM-DD";

/** The first day of `period` (YYYY-MM-DD), given today; null for everything. */
export function periodStart(period: Period, today: string): string | null {
  const last = dayjs(today);
  switch (period) {
    case Period.MONTH:
      return last.subtract(1, "month").format(DAY_FORMAT);
    case Period.HALF_YEAR:
      return last.subtract(6, "month").format(DAY_FORMAT);
    case Period.YEAR_TO_DATE:
      return last.startOf("year").format(DAY_FORMAT);
    case Period.YEAR:
      return last.subtract(1, "year").format(DAY_FORMAT);
    case Period.ALL:
      return null;
  }
}

/** The URL query showing `period`, keeping the rest of `current`. */
export function periodSearch(current: URLSearchParams, period: Period): URLSearchParams {
  const updated = new URLSearchParams(current);
  if (period === Period.ALL) {
    updated.delete(PERIOD_PARAM);
  } else {
    updated.set(PERIOD_PARAM, period);
  }
  return updated;
}

/** The period in the URL (everything when it has none or an unknown one), and a way to change it. */
export function usePeriod(): [Period, (period: Period) => void] {
  const [params, setParams] = useSearchParams();
  const value = params.get(PERIOD_PARAM);
  const period = Object.values(Period).find((known) => known === value) ?? Period.ALL;
  // Replacing the history entry: Back leaves the page instead of stepping through periods.
  const setPeriod = (next: Period) => setParams((current) => periodSearch(current, next), { replace: true });
  return [period, setPeriod];
}

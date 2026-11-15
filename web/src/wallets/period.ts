import dayjs from "dayjs";
import { useSearchParams } from "react-router";

import { formatDate } from "../ui/format";
import { PAGE_PARAM } from "../ui/pagination";
import { useUpdateQuery } from "../ui/url";

// The period a wallet page shows (the value chart and the operations): a preset ending today, as on most brokers' and
// finance sites' charts, or chosen dates. It is kept in the URL (?period=1Y, or ?from=2023-01-01&to=2023-12-31), so a
// view can be bookmarked and shared.
export enum Period {
  MONTH = "1M",
  HALF_YEAR = "6M",
  YEAR_TO_DATE = "YTD",
  YEAR = "1Y",
  ALL = "All",
}

/** Days from `start` to `end` (YYYY-MM-DD, both included); null leaves that side open. */
export type DayRange = { start: string | null; end: string | null };

const PERIOD_PARAM = "period";
// The period shown when the URL names none: recent enough to read, long enough for returns to mean something.
const DEFAULT_PERIOD = Period.HALF_YEAR;
const FROM_PARAM = "from";
const TO_PARAM = "to";
const DAY_FORMAT = "YYYY-MM-DD";

/** The days `period` covers, given today. */
export function periodRange(period: Period, today: string): DayRange {
  const last = dayjs(today);
  const since = (start: dayjs.Dayjs | null) => ({ start: start && start.format(DAY_FORMAT), end: null });
  switch (period) {
    case Period.MONTH:
      return since(last.subtract(1, "month"));
    case Period.HALF_YEAR:
      return since(last.subtract(6, "month"));
    case Period.YEAR_TO_DATE:
      return since(last.startOf("year"));
    case Period.YEAR:
      return since(last.subtract(1, "year"));
    case Period.ALL:
      return since(null);
  }
}

/** Whether `day` (YYYY-MM-DD) is in `range`. */
export function inRange(day: string, range: DayRange): boolean {
  return (range.start === null || day >= range.start) && (range.end === null || day <= range.end);
}

/** The range in words, after e.g. "No operations": "since 1 Jan 2023", "from 1 Jan 2023 to 31 Dec 2023". */
export function describeRange(range: DayRange): string {
  const { start, end } = range;
  if (start !== null && end !== null) {
    return `from ${formatDate(start)} to ${formatDate(end)}`;
  }
  if (start !== null) {
    return `since ${formatDate(start)}`;
  }
  return end !== null ? `until ${formatDate(end)}` : "";
}

/** Whether `range` is open on both sides: everything. */
export function isEverything(range: DayRange): boolean {
  return range.start === null && range.end === null;
}

/** The URL query showing a preset period or chosen dates, keeping the rest of `current` but its page: back to the first. */
export function periodSearch(current: URLSearchParams, choice: Period | DayRange): URLSearchParams {
  const updated = new URLSearchParams(current);
  [PERIOD_PARAM, FROM_PARAM, TO_PARAM, PAGE_PARAM].forEach((param) => updated.delete(param));
  // Clearing both dates means everything, not back to the default.
  const preset = typeof choice === "string" ? choice : isEverything(choice) ? Period.ALL : null;
  if (preset !== null) {
    if (preset !== DEFAULT_PERIOD) {
      updated.set(PERIOD_PARAM, preset);
    }
  } else if (typeof choice !== "string") {
    if (choice.start !== null) {
      updated.set(FROM_PARAM, choice.start);
    }
    if (choice.end !== null) {
      updated.set(TO_PARAM, choice.end);
    }
  }
  return updated;
}

/**
 * The period in the URL: chosen dates if it has any, else its preset (the last six months when it has none or an unknown one;
 * an invalid date is ignored). `period` is null for chosen dates. `choose` changes it.
 */
export function usePeriod(today: string) {
  const [params] = useSearchParams();
  const updateQuery = useUpdateQuery();
  const from = day(params.get(FROM_PARAM));
  const to = day(params.get(TO_PARAM));
  const preset = Object.values(Period).find((known) => known === params.get(PERIOD_PARAM)) ?? DEFAULT_PERIOD;
  const period = from === null && to === null ? preset : null;
  const range = period === null ? { start: from, end: to } : periodRange(period, today);
  const choose = (choice: Period | DayRange) => updateQuery((current) => periodSearch(current, choice));
  return { period, range, choose, params };
}

function day(value: string | null): string | null {
  return value !== null && dayjs(value, DAY_FORMAT, true).isValid() ? value : null;
}

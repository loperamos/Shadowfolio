// How values are written in the UI, in one place so every page shows them the same way.

import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat";

// Lets dates be parsed in a given format (e.g. typed as DD/MM/YYYY).
dayjs.extend(customParseFormat);

const DATE_TIME = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const DATE = new Intl.DateTimeFormat(undefined, { dateStyle: "medium" });

/** A timestamp from the API, in the viewer's time zone. */
export function formatDateTime(isoTimestamp: string): string {
  return DATE_TIME.format(new Date(isoTimestamp));
}

/** A calendar date from the API (YYYY-MM-DD), shown as that same day whatever the time zone. */
export function formatDate(isoDate: string): string {
  return DATE.format(new Date(`${isoDate}T00:00:00`));
}

/**
 * A decimal string cut to at most `places` decimals, for display only (e.g. long exchange rates).
 * Works on the text, so the value never goes through a float.
 */
export function shortDecimal(value: string, places: number): string {
  const dot = value.indexOf(".");
  return dot === -1 ? value : value.slice(0, dot + 1 + places).replace(/\.?0+$/, "");
}

/** How date inputs show (and accept typed) dates, e.g. 24/06/2024, as on European statements. */
export const DATE_INPUT_FORMAT = "DD/MM/YYYY";

// Value formats of Mantine's date and time inputs.
const DATE_VALUE_FORMAT = "YYYY-MM-DD";
const TIME_VALUE_FORMAT = "HH:mm";

/** Reads a date typed in DATE_INPUT_FORMAT; null if it is not a valid date. */
export function parseDateInput(text: string): string | null {
  const date = dayjs(text, DATE_INPUT_FORMAT, true);
  return date.isValid() ? date.format(DATE_VALUE_FORMAT) : null;
}

/** Today in the viewer's time zone, as a date input value. */
export function todayAsInputValue(): string {
  return dayjs().format(DATE_VALUE_FORMAT);
}

/** The current local time, as a time input value (to the minute). */
export function nowAsTimeValue(): string {
  return dayjs().format(TIME_VALUE_FORMAT);
}

/** A local date and time from date and time input values, as a UTC timestamp for the API. */
export function toUtcTimestamp(date: string, time: string): string {
  return dayjs(`${date} ${time}`).toISOString();
}

/** Whether a local date and time from date and time input values is later than now. */
export function isInFuture(date: string, time: string): boolean {
  return dayjs(`${date} ${time}`).isAfter(dayjs());
}

/** The local date of an API timestamp, as a date input value. */
export function dateInputValueOf(isoTimestamp: string): string {
  return dayjs(isoTimestamp).format(DATE_VALUE_FORMAT);
}

/** The local time of an API timestamp, as a time input value. */
export function timeInputValueOf(isoTimestamp: string): string {
  return dayjs(isoTimestamp).format(TIME_VALUE_FORMAT);
}

// How values are written in the UI, in one place so every page shows them the same way.

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

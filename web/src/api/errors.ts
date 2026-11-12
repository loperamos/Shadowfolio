import type { ErrorResponse } from "./generated";

const FALLBACK_MESSAGE = "Something went wrong.";

/** A readable message from an error response of the API (see ErrorResponse in the backend). */
export function apiErrorMessage(error: unknown): string {
  const detail = (error as ErrorResponse | undefined)?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join("; ");
  }
  return FALLBACK_MESSAGE;
}

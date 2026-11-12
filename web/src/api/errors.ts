import type { ValidationError } from "./generated";

// What the backend returns on errors: a message for broken business rules, or FastAPI's list of
// validation errors for malformed requests.
type ErrorBody = { detail?: string | ValidationError[] };

const FALLBACK_MESSAGE = "Something went wrong.";

/** A readable message from an error response of the API. */
export function apiErrorMessage(error: unknown): string {
  const detail = (error as ErrorBody | undefined)?.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => `${item.loc.at(-1)}: ${item.msg}`).join("; ");
  }
  return FALLBACK_MESSAGE;
}

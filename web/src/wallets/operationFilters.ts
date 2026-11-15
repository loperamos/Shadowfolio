import { useSearchParams } from "react-router";

import { PAGE_PARAM } from "../ui/pagination";
import { useUpdateQuery } from "../ui/url";

// Filters of a wallet's operations, besides the period, kept in the URL (?type=buy,sell&symbol=NVDA) so a view can
// be shared. Changing one goes back to the first page.
const TYPE_PARAM = "type";
const SYMBOL_PARAM = "symbol";
const LIST_SEPARATOR = ",";

export type OperationFilters = { types: string[]; symbol: string | null };

/** The URL query showing only the operations in `symbol`, e.g. to link to a wallet's trades in it. */
export function symbolFilterSearch(symbol: string): string {
  return new URLSearchParams({ [SYMBOL_PARAM]: symbol }).toString();
}

/** The URL query without the operation filters (nor the page), keeping the rest of `current`. */
export function withoutOperationFilters(current: URLSearchParams): URLSearchParams {
  const updated = new URLSearchParams(current);
  [TYPE_PARAM, SYMBOL_PARAM, PAGE_PARAM].forEach((param) => updated.delete(param));
  return updated;
}

/** The operation filters in the URL, and ways to change each (leaving the other as it is). */
export function useOperationFilters() {
  const [params] = useSearchParams();
  const updateQuery = useUpdateQuery();
  const types = params.get(TYPE_PARAM)?.split(LIST_SEPARATOR).filter(Boolean) ?? [];
  const filters: OperationFilters = { types, symbol: params.get(SYMBOL_PARAM) };
  const set = (param: string, value: string) =>
    updateQuery((current) => {
      const updated = new URLSearchParams(current);
      updated.delete(PAGE_PARAM);
      if (value) {
        updated.set(param, value);
      } else {
        updated.delete(param);
      }
      return updated;
    });
  const setTypes = (next: string[]) => set(TYPE_PARAM, next.join(LIST_SEPARATOR));
  const setSymbol = (next: string | null) => set(SYMBOL_PARAM, next ?? "");
  return { filters, setTypes, setSymbol };
}

/** Whether `operation` passes `filters` (no filter lets everything through). */
export function matches(operation: { type: string; symbol?: string | null }, filters: OperationFilters): boolean {
  return (filters.types.length === 0 || filters.types.includes(operation.type)) && (filters.symbol === null || operation.symbol === filters.symbol);
}

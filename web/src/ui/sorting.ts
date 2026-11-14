import { useSearchParams } from "react-router";

import { useUpdateQuery } from "./url";

// How a table is sorted, kept in the URL (?sort=value&order=desc) when not its default, so a view can be shared.
export enum SortOrder {
  ASCENDING = "asc",
  DESCENDING = "desc",
}

export type Sort<K extends string> = { key: K; order: SortOrder };

const SORT_PARAM = "sort";
const ORDER_PARAM = "order";

/**
 * The table's sort from the URL (`fallback` when it has none, or an unknown one), and `sortBy(key, firstOrder)`, as on
 * clicking a column's header: the same column again reverses it; another sorts by it in `firstOrder` (e.g. largest
 * first for amounts).
 */
export function useSort<K extends string>(keys: readonly K[], fallback: Sort<K>): [Sort<K>, (key: K, firstOrder: SortOrder) => void] {
  const [params] = useSearchParams();
  const updateQuery = useUpdateQuery();
  const key = keys.find((known) => known === params.get(SORT_PARAM));
  const order = Object.values(SortOrder).find((known) => known === params.get(ORDER_PARAM));
  const sort = key !== undefined && order !== undefined ? { key, order } : fallback;

  function sortBy(next: K, firstOrder: SortOrder) {
    const reversed = sort.order === SortOrder.ASCENDING ? SortOrder.DESCENDING : SortOrder.ASCENDING;
    const nextSort = next === sort.key ? { key: next, order: reversed } : { key: next, order: firstOrder };
    updateQuery((current) => {
      const updated = new URLSearchParams(current);
      if (nextSort.key === fallback.key && nextSort.order === fallback.order) {
        updated.delete(SORT_PARAM);
        updated.delete(ORDER_PARAM);
      } else {
        updated.set(SORT_PARAM, nextSort.key);
        updated.set(ORDER_PARAM, nextSort.order);
      }
      return updated;
    });
  }
  return [sort, sortBy];
}

/**
 * `rows` sorted by the value `valueOf` gives each, in `order`. Rows without a value (e.g. still loading) go last
 * either way, and rows with equal values keep their order.
 */
export function sorted<T>(rows: readonly T[], valueOf: (row: T) => number | string | null, order: SortOrder): T[] {
  const direction = order === SortOrder.ASCENDING ? 1 : -1;
  return [...rows].sort((a, b) => {
    const x = valueOf(a);
    const y = valueOf(b);
    if (x === null || y === null) {
      return x === y ? 0 : x === null ? 1 : -1;
    }
    const comparison = typeof x === "string" && typeof y === "string" ? x.localeCompare(y) : Number(x) - Number(y);
    return comparison * direction;
  });
}

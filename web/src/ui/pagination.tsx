import { Group, Pagination, Text } from "@mantine/core";
import { Link, useSearchParams } from "react-router";

// Long lists are shown a page at a time, as on bank and broker statements; the page is kept in the URL (?page=2).
export const PAGE_PARAM = "page";
const PAGE_SIZE = 50;
const FIRST_PAGE = 1;

/** The URL query showing `page`, keeping the rest of `current` (the first page is the default, so it has none). */
function pageSearch(current: URLSearchParams, page: number): string {
  const updated = new URLSearchParams(current);
  if (page === FIRST_PAGE) {
    updated.delete(PAGE_PARAM);
  } else {
    updated.set(PAGE_PARAM, String(page));
  }
  return updated.toString();
}

/** The page of `rows` in the URL (the first when it has none; the last when it is past the end), and the links to the others. */
export function usePage<T>(rows: readonly T[]) {
  const [params] = useSearchParams();
  const pageCount = Math.max(FIRST_PAGE, Math.ceil(rows.length / PAGE_SIZE));
  const asked = Number.parseInt(params.get(PAGE_PARAM) ?? "", 10);
  const page = Number.isNaN(asked) ? FIRST_PAGE : Math.min(Math.max(asked, FIRST_PAGE), pageCount);
  const first = (page - 1) * PAGE_SIZE;
  const pageRows = rows.slice(first, first + PAGE_SIZE);
  const links = <PageLinks page={page} pageCount={pageCount} first={first} shown={pageRows.length} total={rows.length} params={params} />;
  return { pageRows, links };
}

type LinksProps = { page: number; pageCount: number; first: number; shown: number; total: number; params: URLSearchParams };

/** Which rows are shown and links to every page, as real links (they can be opened in a new tab); nothing for one page. */
function PageLinks({ page, pageCount, first, shown, total, params }: LinksProps) {
  if (pageCount === FIRST_PAGE) {
    return null;
  }
  const linkTo = (target: number) => ({ component: Link, to: { search: pageSearch(params, target) }, replace: true });
  const edges = { previous: page - 1, next: page + 1, first: FIRST_PAGE, last: pageCount };
  return (
    <Group justify="space-between" mt="sm">
      <Text c="dimmed" size="sm">
        {first + 1}–{first + shown} of {total}
      </Text>
      <Pagination
        total={pageCount}
        value={page}
        // The links change the page; nothing else to do on a click.
        onChange={() => undefined}
        getItemProps={linkTo}
        getControlProps={(control) => (edges[control] >= FIRST_PAGE && edges[control] <= pageCount ? linkTo(edges[control]) : {})}
      />
    </Group>
  );
}

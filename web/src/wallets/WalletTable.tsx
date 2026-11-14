import { Alert, Anchor, Checkbox, Group, Loader, Table, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { Link, useSearchParams } from "react-router";

import type { WalletResponse } from "../api/generated";
import { walletPath } from "../routes";
import { Money } from "../ui/Money";
import { SortableTh } from "../ui/SortableTh";
import { sorted, SortOrder, useSort } from "../ui/sorting";
import { ICON_SIZE, SEARCH_INPUT_WIDTH, TABLE_MIN_WIDTH } from "../ui/theme";
import { HindsightBadge } from "./HindsightBadges";
import { type ValuationState, useWalletValuations } from "./useWalletValuation";
import { WalletActionsMenu } from "./WalletActionsMenu";
import { WalletDayChange, WalletGain, WalletValue } from "./WalletValue";

// Columns the wallets can be sorted by; by default by name, A to Z.
enum WalletColumn {
  NAME = "name",
  CASH = "cash",
  VALUE = "value",
  TODAY = "today",
  GAIN = "gain",
}
const DEFAULT_SORT = { key: WalletColumn.NAME, order: SortOrder.ASCENDING };
// The name search, kept in the URL (?q=) so a filtered list can be shared.
const SEARCH_PARAM = "q";

type Props = {
  wallets: WalletResponse[] | null;
  error: string | null;
  selectedIds: ReadonlySet<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onRename: (wallet: WalletResponse) => void;
  onSettings: (wallet: WalletResponse) => void;
  onImport: (wallet: WalletResponse) => void;
  onDuplicate: (wallet: WalletResponse) => void;
  onDelete: (wallets: WalletResponse[]) => void;
};

export function WalletTable({ wallets, error, selectedIds, onSelectionChange, onRename, onSettings, onImport, onDuplicate, onDelete }: Props) {
  const valuations = useWalletValuations((wallets ?? []).map((wallet) => wallet.id));
  const [sort, sortBy] = useSort(Object.values(WalletColumn), DEFAULT_SORT);
  const [params, setParams] = useSearchParams();
  const search = params.get(SEARCH_PARAM) ?? "";
  if (error) {
    return <Alert color="red">{error}</Alert>;
  }
  if (wallets === null) {
    return <Loader />;
  }
  if (wallets.length === 0) {
    return <Text c="dimmed">No wallets yet.</Text>;
  }

  const matching = wallets.filter((wallet) => wallet.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()));
  const shown = sorted(matching, walletSortValue(sort.key, valuations), sort.order);
  // Selecting all selects the wallets shown.
  const allSelected = shown.length > 0 && shown.every((wallet) => selectedIds.has(wallet.id));
  const someSelected = !allSelected && shown.some((wallet) => selectedIds.has(wallet.id));

  // Replacing the history entry while typing, so Back leaves the page.
  const setSearch = (value: string) => setParams((current) => searchFor(current, value), { replace: true });

  const th = (column: WalletColumn, label: string, firstOrder = SortOrder.DESCENDING, align: "left" | "right" = "right") => (
    <SortableTh column={column} sort={sort} onSort={sortBy} firstOrder={firstOrder} align={align}>
      {label}
    </SortableTh>
  );

  function toggle(id: string) {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onSelectionChange(next);
  }

  return (
    <>
    <TextInput
      aria-label="Search wallets by name"
      placeholder="Search by name"
      leftSection={<IconSearch size={ICON_SIZE} />}
      w={SEARCH_INPUT_WIDTH}
      mb="sm"
      value={search}
      onChange={(event) => setSearch(event.currentTarget.value)}
    />
    {shown.length === 0 ? (
      <Text c="dimmed">
        No wallets match “{search}”.{" "}
        <Anchor component={Link} to={{ search: searchFor(params, "").toString() }} replace>
          Show all
        </Anchor>
      </Text>
    ) : (
    <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
      <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          <Table.Th w={40}>
            <Checkbox
              aria-label="Select all wallets"
              checked={allSelected}
              indeterminate={someSelected}
              onChange={() => onSelectionChange(allSelected ? new Set() : new Set(shown.map((wallet) => wallet.id)))}
            />
          </Table.Th>
          {th(WalletColumn.NAME, "Name", SortOrder.ASCENDING, "left")}
          {th(WalletColumn.CASH, "Cash")}
          {th(WalletColumn.VALUE, "Value")}
          {th(WalletColumn.TODAY, "Today")}
          {th(WalletColumn.GAIN, "Gain")}
          <Table.Th>Holdings</Table.Th>
          <Table.Th w={40} />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {shown.map((wallet) => (
          <Table.Tr key={wallet.id} bg={selectedIds.has(wallet.id) ? "var(--mantine-primary-color-light)" : undefined}>
            <Table.Td>
              <Checkbox aria-label={`Select ${wallet.name}`} checked={selectedIds.has(wallet.id)} onChange={() => toggle(wallet.id)} />
            </Table.Td>
            <Table.Td>
              <Group gap="xs" wrap="nowrap">
                <Anchor component={Link} to={walletPath(wallet.id)}>
                  {wallet.name}
                </Anchor>
                {wallet.hindsight && <HindsightBadge />}
              </Group>
            </Table.Td>
            <Table.Td ta="right">
              <Money amount={wallet.cash} currency={wallet.currency} />
            </Table.Td>
            <WalletValuationCells valuation={valuations[wallet.id] ?? LOADING} />
            <Table.Td>
              {Object.entries(wallet.holdings)
                .map(([symbol, quantity]) => `${symbol} ${quantity}`)
                .join(", ") || <Text c="dimmed">None</Text>}
            </Table.Td>
            <Table.Td>
              <WalletActionsMenu wallet={wallet} onRename={onRename} onSettings={onSettings} onImport={onImport} onDuplicate={onDuplicate} onDelete={onDelete} />
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
      </Table>
    </Table.ScrollContainer>
    )}
    </>
  );
}

const LOADING: ValuationState = { status: "loading" };

/** The URL query searching for `value`, keeping the rest of `current`. */
function searchFor(current: URLSearchParams, value: string): URLSearchParams {
  const updated = new URLSearchParams(current);
  if (value) {
    updated.set(SEARCH_PARAM, value);
  } else {
    updated.delete(SEARCH_PARAM);
  }
  return updated;
}

/** What a wallet is sorted by in `column`; null while its valuation is not there. Amounts are compared as they are,
 * whatever each wallet's currency. */
function walletSortValue(column: WalletColumn, valuations: Record<string, ValuationState>) {
  return (wallet: WalletResponse): number | string | null => {
    const state = valuations[wallet.id];
    const valuation = state?.status === "loaded" ? state.valuation : null;
    switch (column) {
      case WalletColumn.NAME:
        return wallet.name;
      case WalletColumn.CASH:
        return Number(wallet.cash);
      case WalletColumn.VALUE:
        return valuation && Number(valuation.total);
      case WalletColumn.TODAY:
        return valuation?.day_change != null ? Number(valuation.day_change) : null;
      case WalletColumn.GAIN:
        return valuation && Number(valuation.gain);
    }
  };
}

/** The Value, Today and Gain cells of a row, from one valuation of the wallet. */
function WalletValuationCells({ valuation }: { valuation: ValuationState }) {
  return (
    <>
      <Table.Td ta="right">
        <WalletValue state={valuation} />
      </Table.Td>
      <Table.Td ta="right">
        <WalletDayChange state={valuation} />
      </Table.Td>
      <Table.Td ta="right">
        <WalletGain state={valuation} />
      </Table.Td>
    </>
  );
}

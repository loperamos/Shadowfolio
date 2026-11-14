import { Alert, Anchor, Checkbox, Group, Loader, Table, Text } from "@mantine/core";
import { Link } from "react-router";

import type { WalletResponse } from "../api/generated";
import { walletPath } from "../routes";
import { Money } from "../ui/Money";
import { TABLE_MIN_WIDTH } from "../ui/theme";
import { HindsightBadge } from "./HindsightBadges";
import { useWalletValuation } from "./useWalletValuation";
import { WalletActionsMenu } from "./WalletActionsMenu";
import { WalletDayChange, WalletGain, WalletValue } from "./WalletValue";

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
  if (error) {
    return <Alert color="red">{error}</Alert>;
  }
  if (wallets === null) {
    return <Loader />;
  }
  if (wallets.length === 0) {
    return <Text c="dimmed">No wallets yet.</Text>;
  }

  const allSelected = wallets.every((wallet) => selectedIds.has(wallet.id));
  const someSelected = !allSelected && wallets.some((wallet) => selectedIds.has(wallet.id));

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
    <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
      <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          <Table.Th w={40}>
            <Checkbox
              aria-label="Select all wallets"
              checked={allSelected}
              indeterminate={someSelected}
              onChange={() => onSelectionChange(allSelected ? new Set() : new Set(wallets.map((wallet) => wallet.id)))}
            />
          </Table.Th>
          <Table.Th>Name</Table.Th>
          <Table.Th ta="right">Cash</Table.Th>
          <Table.Th ta="right">Value</Table.Th>
          <Table.Th ta="right">Today</Table.Th>
          <Table.Th ta="right">Gain</Table.Th>
          <Table.Th>Holdings</Table.Th>
          <Table.Th w={40} />
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {wallets.map((wallet) => (
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
            <WalletValuationCells walletId={wallet.id} />
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
  );
}

/** The Value, Today and Gain cells of a row, from one valuation of the wallet. */
function WalletValuationCells({ walletId }: { walletId: string }) {
  const valuation = useWalletValuation(walletId);
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

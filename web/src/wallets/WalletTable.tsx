import { ActionIcon, Alert, Checkbox, Loader, Menu, Table, Text } from "@mantine/core";
import { IconCopy, IconDots, IconTrash } from "@tabler/icons-react";

import type { WalletResponse } from "../api/generated";
import { ICON_SIZE } from "../ui/theme";

type Props = {
  wallets: WalletResponse[] | null;
  error: string | null;
  selectedIds: ReadonlySet<string>;
  onSelectionChange: (ids: Set<string>) => void;
  onDuplicate: (wallet: WalletResponse) => void;
  onDelete: (wallets: WalletResponse[]) => void;
};

export function WalletTable({ wallets, error, selectedIds, onSelectionChange, onDuplicate, onDelete }: Props) {
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
            <Table.Td>{wallet.name}</Table.Td>
            <Table.Td ta="right">
              {wallet.cash} {wallet.currency}
            </Table.Td>
            <Table.Td>
              {Object.entries(wallet.holdings)
                .map(([symbol, quantity]) => `${symbol} ${quantity}`)
                .join(", ") || <Text c="dimmed">None</Text>}
            </Table.Td>
            <Table.Td>
              <Menu position="bottom-end">
                <Menu.Target>
                  <ActionIcon variant="subtle" color="gray" aria-label={`Actions for ${wallet.name}`}>
                    <IconDots size={ICON_SIZE} />
                  </ActionIcon>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item leftSection={<IconCopy size={ICON_SIZE} />} onClick={() => onDuplicate(wallet)}>
                    Duplicate
                  </Menu.Item>
                  <Menu.Item color="red" leftSection={<IconTrash size={ICON_SIZE} />} onClick={() => onDelete([wallet])}>
                    Delete
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

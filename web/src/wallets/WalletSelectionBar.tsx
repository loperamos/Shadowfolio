import { Button, Group, Paper, Text, Tooltip } from "@mantine/core";
import { IconCopy, IconTrash } from "@tabler/icons-react";

import type { WalletResponse } from "../api/generated";
import { ICON_SIZE } from "../ui/theme";

type Props = {
  selected: WalletResponse[];
  onDuplicate: (wallet: WalletResponse) => void;
  onDelete: (wallets: WalletResponse[]) => void;
  onClear: () => void;
};

/** Actions for the selected wallets; shown only while at least one is selected. */
export function WalletSelectionBar({ selected, onDuplicate, onDelete, onClear }: Props) {
  if (selected.length === 0) {
    return null;
  }
  const single = selected.length === 1 ? selected[0] : null;

  return (
    <Paper withBorder p="xs" mb="sm">
      <Group justify="space-between">
        <Text fw={500}>{selected.length} selected</Text>
        <Group gap="xs">
          <Tooltip label="Select one wallet to duplicate" disabled={single !== null}>
            {/* The wrapper keeps the tooltip working while the button is disabled. */}
            <span>
              <Button variant="default" size="xs" leftSection={<IconCopy size={ICON_SIZE} />} disabled={single === null} onClick={() => single && onDuplicate(single)}>
                Duplicate
              </Button>
            </span>
          </Tooltip>
          <Button color="red" variant="light" size="xs" leftSection={<IconTrash size={ICON_SIZE} />} onClick={() => onDelete(selected)}>
            Delete
          </Button>
          <Button variant="subtle" color="gray" size="xs" onClick={onClear}>
            Clear
          </Button>
        </Group>
      </Group>
    </Paper>
  );
}

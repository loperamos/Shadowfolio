import { Button, Group, Paper, Text, Tooltip } from "@mantine/core";
import { IconCopy, IconScale, IconTrash } from "@tabler/icons-react";
import { Link } from "react-router";

import type { WalletResponse } from "../api/generated";
import { comparePath } from "../routes";
import { ICON_SIZE } from "../ui/theme";

// Fewest wallets a comparison takes.
const MIN_TO_COMPARE = 2;

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
  const comparable = selected.length >= MIN_TO_COMPARE;

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
          <Tooltip label="Select two or more wallets to compare" disabled={comparable}>
            <span>
              {/* A link, so a comparison opens in a new tab too. */}
              {comparable ? (
                <Button component={Link} to={comparePath(selected.map((wallet) => wallet.id))} variant="default" size="xs" leftSection={<IconScale size={ICON_SIZE} />}>
                  Compare
                </Button>
              ) : (
                <Button variant="default" size="xs" leftSection={<IconScale size={ICON_SIZE} />} disabled>
                  Compare
                </Button>
              )}
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

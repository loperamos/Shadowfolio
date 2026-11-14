import { ActionIcon, Menu } from "@mantine/core";
import { IconDots, IconPencil, IconTrash } from "@tabler/icons-react";

import type { OperationResponse } from "../api/generated";
import { ICON_SIZE } from "../ui/theme";
import { isEditable } from "./OperationModal";

type Props = {
  operation: OperationResponse;
  onEdit: (operation: OperationResponse) => void;
  onDelete: (operation: OperationResponse) => void;
};

// Why an operation cannot be edited or deleted, shown in its menu.
const FROM_MARKET_DATA = "Added from market data; it follows the rest of the history.";
const FROM_STATEMENT = "Imported from a broker statement.";

/** The ⋯ menu of one operation in a wallet's history. Operations not recorded by hand keep it, with its actions
 * disabled and the reason. */
export function OperationActionsMenu({ operation, onEdit, onDelete }: Props) {
  const reason = isEditable(operation) ? null : operation.automatic ? FROM_MARKET_DATA : FROM_STATEMENT;
  return (
    <Menu position="bottom-end">
      <Menu.Target>
        <ActionIcon variant="subtle" color="gray" aria-label="Operation actions">
          <IconDots size={ICON_SIZE} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        {reason && <Menu.Label>{reason}</Menu.Label>}
        <Menu.Item leftSection={<IconPencil size={ICON_SIZE} />} disabled={reason !== null} onClick={() => onEdit(operation)}>
          Edit
        </Menu.Item>
        <Menu.Item color="red" leftSection={<IconTrash size={ICON_SIZE} />} disabled={reason !== null} onClick={() => onDelete(operation)}>
          Delete
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

import { ActionIcon, Menu } from "@mantine/core";
import { IconDots, IconPencil, IconTrash } from "@tabler/icons-react";

import type { OperationResponse } from "../api/generated";
import { ICON_SIZE } from "../ui/theme";

type Props = {
  operation: OperationResponse;
  onEdit: (operation: OperationResponse) => void;
  onDelete: (operation: OperationResponse) => void;
};

/** The ⋯ menu of one operation in a wallet's history. */
export function OperationActionsMenu({ operation, onEdit, onDelete }: Props) {
  return (
    <Menu position="bottom-end">
      <Menu.Target>
        <ActionIcon variant="subtle" color="gray" aria-label="Operation actions">
          <IconDots size={ICON_SIZE} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item leftSection={<IconPencil size={ICON_SIZE} />} onClick={() => onEdit(operation)}>
          Edit
        </Menu.Item>
        <Menu.Item color="red" leftSection={<IconTrash size={ICON_SIZE} />} onClick={() => onDelete(operation)}>
          Delete
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

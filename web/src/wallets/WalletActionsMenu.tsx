import { ActionIcon, Menu } from "@mantine/core";
import { IconCopy, IconDots, IconPencil, IconSettings, IconTrash } from "@tabler/icons-react";

import type { WalletResponse } from "../api/generated";
import { ICON_SIZE } from "../ui/theme";

type Props = {
  wallet: WalletResponse;
  onRename: (wallet: WalletResponse) => void;
  onSettings: (wallet: WalletResponse) => void;
  onDuplicate: (wallet: WalletResponse) => void;
  onDelete: (wallets: WalletResponse[]) => void;
};

/** The ⋯ menu with a wallet's actions, the same in the wallet list and on the wallet's page. */
export function WalletActionsMenu({ wallet, onRename, onSettings, onDuplicate, onDelete }: Props) {
  return (
    <Menu position="bottom-end">
      <Menu.Target>
        <ActionIcon variant="subtle" color="gray" aria-label={`Actions for ${wallet.name}`}>
          <IconDots size={ICON_SIZE} />
        </ActionIcon>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item leftSection={<IconPencil size={ICON_SIZE} />} onClick={() => onRename(wallet)}>
          Rename
        </Menu.Item>
        <Menu.Item leftSection={<IconSettings size={ICON_SIZE} />} onClick={() => onSettings(wallet)}>
          Settings
        </Menu.Item>
        <Menu.Item leftSection={<IconCopy size={ICON_SIZE} />} onClick={() => onDuplicate(wallet)}>
          Duplicate
        </Menu.Item>
        <Menu.Item color="red" leftSection={<IconTrash size={ICON_SIZE} />} onClick={() => onDelete([wallet])}>
          Delete
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

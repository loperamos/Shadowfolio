import { Alert, Button, Group, Modal, Stack, Text } from "@mantine/core";
import { useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { deleteWallet, type WalletResponse } from "../api/generated";

type Props = {
  wallets: WalletResponse[]; // the wallets to delete; empty when closed
  onClose: () => void;
  onDeleted: () => void;
};

export function DeleteWalletsModal({ wallets, onClose, onDeleted }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  function close() {
    setError(null);
    onClose();
  }

  async function confirm() {
    setDeleting(true);
    setError(null);
    try {
      for (const wallet of wallets) {
        const { error } = await deleteWallet({ path: { wallet_id: wallet.id } });
        if (error) {
          setError(`${wallet.name}: ${apiErrorMessage(error)}`);
          return;
        }
      }
      close();
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setDeleting(false);
      // Some wallets may be gone even if a later one failed, so always refresh.
      onDeleted();
    }
  }

  const title = wallets.length === 1 ? "Delete wallet?" : `Delete ${wallets.length} wallets?`;

  return (
    <Modal opened={wallets.length > 0} onClose={close} title={title}>
      <Stack>
        <Text>
          {wallets.length === 1 ? (
            <>
              <strong>{wallets[0].name}</strong> and its whole history will be deleted.
            </>
          ) : (
            <>
              {wallets.map((wallet) => wallet.name).join(", ")} and their whole history will be deleted.
            </>
          )}{" "}
          This cannot be undone.
        </Text>
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>
            Cancel
          </Button>
          <Button color="red" loading={deleting} onClick={confirm}>
            Delete
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

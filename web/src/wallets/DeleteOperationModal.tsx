import { Alert, Button, Group, Modal, Stack, Text } from "@mantine/core";
import { useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { deleteOperation, type OperationResponse, type WalletResponse } from "../api/generated";
import { formatDateTime } from "../ui/format";

type Props = {
  wallet: WalletResponse;
  operation: OperationResponse | null; // the operation to delete; null when closed
  onClose: () => void;
  onDeleted: () => void;
};

export function DeleteOperationModal({ wallet, operation, onClose, onDeleted }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  function close() {
    setError(null);
    onClose();
  }

  async function confirm() {
    if (!operation) {
      return;
    }
    setDeleting(true);
    setError(null);
    try {
      const { data, error } = await deleteOperation({ path: { wallet_id: wallet.id, operation_id: operation.id } });
      if (data) {
        close();
        onDeleted();
      } else {
        setError(apiErrorMessage(error));
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Modal opened={operation !== null} onClose={close} title="Delete operation?">
      {operation && (
        <Stack>
          <Text>
            The {describe(operation, wallet.currency)} on {formatDateTime(operation.timestamp)} will be removed, and the wallet&apos;s cash and
            holdings recalculated. This cannot be undone.
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
      )}
    </Modal>
  );
}

/** E.g. "buy of 8 NVDA" or "deposit of 3000 EUR". */
function describe(operation: OperationResponse, walletCurrency: string): string {
  return operation.symbol != null
    ? `${operation.type} of ${operation.quantity} ${operation.symbol}`
    : `${operation.type} of ${operation.amount} ${walletCurrency}`;
}

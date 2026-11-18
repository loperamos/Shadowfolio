import { Alert, Button, Group, Modal, Stack, Text } from "@mantine/core";
import { useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { type DataProvider, deleteProviderKey } from "../api/generated";
import { PROVIDERS } from "./providers";

type Props = { provider: DataProvider | null; onClose: () => void; onRemoved: () => void };

/** Asks before removing a key: what it fetched stops until a key is connected again. */
export function RemoveKeyModal({ provider, onClose, onRemoved }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const info = provider && PROVIDERS[provider];

  function close() {
    setError(null);
    onClose();
  }

  async function confirm() {
    if (!provider) {
      return;
    }
    setRemoving(true);
    setError(null);
    try {
      const { error } = await deleteProviderKey({ path: { provider } });
      if (error) {
        setError(apiErrorMessage(error));
      } else {
        close();
        onRemoved();
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setRemoving(false);
    }
  }

  return (
    <Modal opened={info !== null} onClose={close} title={info && `Remove your ${info.name} key?`}>
      {info && (
        <Stack>
          <Text>Shadowfolio forgets the key. {info.withoutIt}</Text>
          {error && <Alert color="red">{error}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button color="red" loading={removing} onClick={confirm}>
              Remove key
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

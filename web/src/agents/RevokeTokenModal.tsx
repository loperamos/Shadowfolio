import { Alert, Button, Group, Modal, Stack, Text } from "@mantine/core";
import { useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { type AccessTokenResponse, revokeAccessToken } from "../api/generated";

type Props = { token: AccessTokenResponse | null; onClose: () => void; onRevoked: () => void };

/** Asks before revoking: agents using the token stop working at once, and it cannot be undone. */
export function RevokeTokenModal({ token, onClose, onRevoked }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [revoking, setRevoking] = useState(false);

  function close() {
    setError(null);
    onClose();
  }

  async function confirm() {
    if (!token) {
      return;
    }
    setRevoking(true);
    setError(null);
    try {
      const { data, error } = await revokeAccessToken({ path: { token_id: token.id } });
      if (data) {
        close();
        onRevoked();
      } else {
        setError(apiErrorMessage(error));
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setRevoking(false);
    }
  }

  return (
    <Modal opened={token !== null} onClose={close} title="Revoke token?">
      {token && (
        <Stack>
          <Text>
            Agents using <strong>{token.name}</strong> will stop working at once. This cannot be undone; you can create
            another token.
          </Text>
          {error && <Alert color="red">{error}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Keep it
            </Button>
            <Button color="red" loading={revoking} onClick={confirm}>
              Revoke token
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

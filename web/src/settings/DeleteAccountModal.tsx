import { Alert, Button, Group, List, Loader, Modal, Stack, Text, TextInput } from "@mantine/core";
import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { deleteMe, listAccessTokens, listWallets } from "../api/generated";
import { useAuth } from "../auth/useAuth";

// What to type to confirm, as GitHub asks for a repository's name before deleting it.
const CONFIRMATION = "DELETE";

type Owned = { wallets: number; tokens: number };
type Props = { opened: boolean; onClose: () => void };

/**
 * Asks before deleting the account, saying what will be lost (how many wallets and agent tokens), and to type DELETE:
 * it cannot be undone. Once deleted, signs out, back to the front page.
 */
export function DeleteAccountModal({ opened, onClose }: Props) {
  const { signOut } = useAuth();
  const [owned, setOwned] = useState<Owned | null>(null);
  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!opened) {
      return;
    }
    let current = true;
    Promise.all([listWallets(), listAccessTokens()])
      .then(([wallets, tokens]) => {
        const active = (tokens.data ?? []).filter((token) => token.revoked_at == null).length;
        if (current) {
          setOwned({ wallets: wallets.data?.length ?? 0, tokens: active });
        }
      })
      .catch(() => current && setOwned(null));
    return () => {
      current = false;
    };
  }, [opened]);

  function close() {
    setTyped("");
    setError(null);
    onClose();
  }

  async function confirm() {
    setDeleting(true);
    setError(null);
    try {
      const { error } = await deleteMe();
      if (error) {
        setError(apiErrorMessage(error));
        return;
      }
      signOut();
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Modal opened={opened} onClose={close} title="Delete your account?">
      <Stack>
        <Text>This deletes, for good:</Text>
        {owned === null ? (
          <Loader size="sm" />
        ) : (
          <List>
            {owned.wallets > 0 && (
              <List.Item>
                {owned.wallets === 1 ? "Your wallet, with all its history and orders" : `Your ${owned.wallets} wallets, with all their history and orders`}
              </List.Item>
            )}
            {owned.tokens > 0 && (
              <List.Item>
                {owned.tokens === 1 ? "Your agent token: agents using it stop at once" : `Your ${owned.tokens} agent tokens: agents using them stop at once`}
              </List.Item>
            )}
            <List.Item>Your saved market-data keys</List.Item>
          </List>
        )}
        <Text>It cannot be undone. Signing in again starts a new, empty account.</Text>
        <TextInput
          label={`Type ${CONFIRMATION} to confirm`}
          autoComplete="off"
          value={typed}
          onChange={(event) => setTyped(event.currentTarget.value)}
          data-autofocus
        />
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>
            Cancel
          </Button>
          <Button color="red" loading={deleting} disabled={typed !== CONFIRMATION} onClick={confirm}>
            Delete my account
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

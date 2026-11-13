import { Alert, Button, Group, Modal, Stack, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { updateWallet, type WalletResponse } from "../api/generated";

type Props = {
  wallet: WalletResponse | null; // the wallet to rename; null when closed
  onClose: () => void;
  onRenamed: (wallet: WalletResponse) => void;
};

export function RenameWalletModal({ wallet, onClose, onRenamed }: Props) {
  return (
    <Modal opened={wallet !== null} onClose={onClose} title="Rename wallet">
      {/* Keyed by wallet, so the form starts fresh for each one. */}
      {wallet && <RenameForm key={wallet.id} wallet={wallet} onClose={onClose} onRenamed={onRenamed} />}
    </Modal>
  );
}

function RenameForm({ wallet, onClose, onRenamed }: { wallet: WalletResponse; onClose: () => void; onRenamed: (wallet: WalletResponse) => void }) {
  const [name, setName] = useState(wallet.name);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { data, error } = await updateWallet({ path: { wallet_id: wallet.id }, body: { name } });
      if (data) {
        onClose();
        onRenamed(data);
      } else {
        setError(apiErrorMessage(error));
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit}>
      <Stack>
        <TextInput label="Name" required data-autofocus value={name} onChange={(e) => setName(e.currentTarget.value)} />
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            Rename
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

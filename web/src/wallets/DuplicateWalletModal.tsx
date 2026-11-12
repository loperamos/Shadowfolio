import { Alert, Button, Group, Modal, Stack, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { copyWallet, type WalletResponse } from "../api/generated";

type Props = {
  wallet: WalletResponse | null; // the wallet to duplicate; null when closed
  onClose: () => void;
  onDuplicated: (copy: WalletResponse) => void;
};

export function DuplicateWalletModal({ wallet, onClose, onDuplicated }: Props) {
  return (
    <Modal opened={wallet !== null} onClose={onClose} title="Duplicate wallet">
      {/* Keyed by wallet, so the form starts fresh for each one. */}
      {wallet && <DuplicateForm key={wallet.id} wallet={wallet} onClose={onClose} onDuplicated={onDuplicated} />}
    </Modal>
  );
}

function DuplicateForm({ wallet, onClose, onDuplicated }: { wallet: WalletResponse; onClose: () => void; onDuplicated: (copy: WalletResponse) => void }) {
  const [name, setName] = useState(`Copy of ${wallet.name}`);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { data, error } = await copyWallet({ path: { wallet_id: wallet.id }, body: { name } });
      if (data) {
        onClose();
        onDuplicated(data);
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
        <TextInput
          label="Name"
          description="The copy starts with the same currency and full history."
          required
          data-autofocus
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
        />
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            Duplicate
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

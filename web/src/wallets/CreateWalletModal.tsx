import { Alert, Button, Group, Modal, Select, Stack, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { createWallet, Currency } from "../api/generated";

const CURRENCIES = Object.values(Currency);
const DEFAULT_CURRENCY = Currency.EUR;
const DEFAULT_CASH = "0";

type Props = {
  opened: boolean;
  onClose: () => void;
  onCreated: () => void;
};

export function CreateWalletModal({ opened, onClose, onCreated }: Props) {
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState<Currency>(DEFAULT_CURRENCY);
  // Kept as text and sent as a string, so amounts stay exact (never through a float).
  const [cash, setCash] = useState(DEFAULT_CASH);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function close() {
    setName("");
    setCurrency(DEFAULT_CURRENCY);
    setCash(DEFAULT_CASH);
    setError(null);
    onClose();
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { data, error } = await createWallet({ body: { name, currency, cash } });
      if (data) {
        close();
        onCreated();
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
    <Modal opened={opened} onClose={close} title="New wallet">
      <form onSubmit={submit}>
        <Stack>
          <TextInput label="Name" required data-autofocus value={name} onChange={(e) => setName(e.currentTarget.value)} />
          <Select
            label="Currency"
            data={CURRENCIES}
            allowDeselect={false}
            value={currency}
            onChange={(value) => value && setCurrency(value as Currency)}
          />
          <TextInput label="Starting cash" inputMode="decimal" value={cash} onChange={(e) => setCash(e.currentTarget.value)} />
          {error && <Alert color="red">{error}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" loading={saving}>
              Create
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

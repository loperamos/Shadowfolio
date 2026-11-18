import { Alert, Button, Group, Modal, Stack, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { type DataProvider, saveProviderKey } from "../api/generated";
import { PROVIDERS } from "./providers";

type Props = { provider: DataProvider | null; replacing: boolean; onClose: () => void; onSaved: () => void };

/** Asks for a provider's key (both parts, for providers with a key id) and saves it, replacing any earlier one. */
export function SaveKeyModal({ provider, replacing, onClose, onSaved }: Props) {
  const [keyId, setKeyId] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const info = provider && PROVIDERS[provider];

  function close() {
    setKeyId("");
    setSecret("");
    setError(null);
    onClose();
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!provider || !info) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const body = { key_id: info.keyIdLabel ? keyId : null, secret };
      const { data, error } = await saveProviderKey({ path: { provider }, body });
      if (data) {
        close();
        onSaved();
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
    <Modal opened={info !== null} onClose={close} title={info && `${replacing ? "Replace" : "Connect"} your ${info.name} key`}>
      {info && (
        <form onSubmit={save}>
          <Stack>
            {info.keyIdLabel && (
              <TextInput label={info.keyIdLabel} required autoComplete="off" spellCheck={false} value={keyId} onChange={(e) => setKeyId(e.currentTarget.value)} data-autofocus />
            )}
            <TextInput
              label={info.secretLabel}
              description="Stored encrypted; never shown again."
              type="password"
              required
              autoComplete="off"
              value={secret}
              onChange={(e) => setSecret(e.currentTarget.value)}
              data-autofocus={info.keyIdLabel ? undefined : true}
            />
            {error && <Alert color="red">{error}</Alert>}
            <Group justify="flex-end">
              <Button variant="default" onClick={close}>
                Cancel
              </Button>
              <Button type="submit" loading={saving}>
                Save
              </Button>
            </Group>
          </Stack>
        </form>
      )}
    </Modal>
  );
}

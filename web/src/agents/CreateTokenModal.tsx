import { Alert, Button, Group, Modal, MultiSelect, SegmentedControl, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { createAccessToken, Scope, type WalletResponse } from "../api/generated";
import { SecretValue } from "../ui/SecretValue";

const SCOPE_OPTIONS = [
  { value: Scope.READ, label: "Read" },
  { value: Scope.TRADING, label: "Trading" },
];
const SCOPE_DESCRIPTIONS: Record<Scope, string> = {
  [Scope.READ]: "Sees its wallets and securities, and previews orders. Cannot place or cancel them: a safe way to try an agent.",
  [Scope.TRADING]: "Also places and cancels orders, now only, within each wallet's rules. Orders change the wallet's simulated history.",
};

type Props = { opened: boolean; wallets: WalletResponse[]; onClose: () => void; onCreated: () => void };

/** Create a token: what it is for, its scope and wallets; then its secret, shown only this once. */
export function CreateTokenModal({ opened, wallets, onClose, onCreated }: Props) {
  return (
    <Modal opened={opened} onClose={onClose} title="Create access token" size="lg">
      {/* Rendered only while open, so it starts empty each time. */}
      {opened && <TokenForm wallets={wallets} onClose={onClose} onCreated={onCreated} />}
    </Modal>
  );
}

function TokenForm({ wallets, onClose, onCreated }: Omit<Props, "opened">) {
  const [name, setName] = useState("");
  const [scope, setScope] = useState<Scope>(Scope.READ);
  const [walletIds, setWalletIds] = useState<string[]>(wallets.length === 1 ? [wallets[0].id] : []);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const { data, error } = await createAccessToken({ body: { name: name.trim(), scope, wallet_ids: walletIds } });
      if (data) {
        setSecret(data.secret);
        onCreated();
      } else {
        setError(apiErrorMessage(error));
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setCreating(false);
    }
  }

  if (secret !== null) {
    return (
      <Stack>
        <Alert color="yellow" title="Copy it now">
          This is the only time the token is shown: Shadowfolio keeps only a fingerprint of it. If you lose it, revoke it
          and create another.
        </Alert>
        <SecretValue value={secret} label="the access token" />
        <Group justify="flex-end">
          <Button onClick={onClose}>Done</Button>
        </Group>
      </Stack>
    );
  }

  const missing = !name.trim() ? "Give the token a name." : walletIds.length === 0 ? "Choose at least one wallet." : null;
  return (
    <form onSubmit={submit}>
      <Stack>
        <TextInput
          label="Name"
          description="What it is for, to recognise it later"
          placeholder="Codex on my laptop"
          required
          data-autofocus
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
        />
        <div>
          <SegmentedControl fullWidth aria-label="Scope" data={SCOPE_OPTIONS} value={scope} onChange={(value) => setScope(value as Scope)} />
          <Text c="dimmed" size="sm" mt="xs">
            {SCOPE_DESCRIPTIONS[scope]}
          </Text>
        </div>
        <MultiSelect
          label="Wallets"
          description="The only wallets it may use"
          required
          data={wallets.map((wallet) => ({ value: wallet.id, label: wallet.name }))}
          value={walletIds}
          onChange={setWalletIds}
        />
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Tooltip label={missing} disabled={missing === null}>
            {/* A wrapper, as a disabled button gets no pointer events to show its tooltip with. */}
            <div>
              <Button type="submit" loading={creating} disabled={missing !== null}>
                Create token
              </Button>
            </div>
          </Tooltip>
        </Group>
      </Stack>
    </form>
  );
}

import { Alert, Button, Group, Modal, Stack, Text, TextInput } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconCalendar } from "@tabler/icons-react";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { copyWallet, type WalletResponse } from "../api/generated";
import { DATE_INPUT_FORMAT, dayAfter, formatDate, parseDateInput, todayAsInputValue, toUtcTimestamp } from "../ui/format";
import { DATE_INPUT_WIDTH, ICON_SIZE } from "../ui/theme";

// The copy keeps what happened up to the end of the chosen day: everything before the next day starts.
const START_OF_DAY = "00:00";

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
  // The history up to the end of this day (YYYY-MM-DD), or all of it when null.
  const [upTo, setUpTo] = useState<string | null>(null);
  // The suggested name follows the date until the name is edited.
  const [editedName, setEditedName] = useState<string | null>(null);
  const name = editedName ?? (upTo ? `${wallet.name} up to ${formatDate(upTo)}` : `Copy of ${wallet.name}`);
  const future = upTo !== null && upTo > todayAsInputValue();
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (future) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const { data, error } = await copyWallet({ path: { wallet_id: wallet.id }, body: { name, before: upTo && toUtcTimestamp(dayAfter(upTo), START_OF_DAY) } });
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
        <TextInput label="Name" required data-autofocus value={name} onChange={(e) => setEditedName(e.currentTarget.value)} />
        <DateInput
          label="History up to"
          w={DATE_INPUT_WIDTH}
          placeholder={DATE_INPUT_FORMAT}
          valueFormat={DATE_INPUT_FORMAT}
          dateParser={parseDateInput}
          leftSection={<IconCalendar size={ICON_SIZE} />}
          value={upTo}
          onChange={setUpTo}
          error={future ? "Not after today" : undefined}
        />
        {/* Below the field rather than its description, which would wrap to the field's narrow width. */}
        <Text c="dimmed" size="sm" mt={-8}>
          Empty copies the whole history. With a date, the copy keeps what happened up to the end of that day, to change
          from there; splits and dividends after it still apply.
        </Text>
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

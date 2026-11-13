import { Alert, Button, Group, Modal, Stack, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { updateWallet, type WalletResponse } from "../api/generated";
import { shiftDecimal } from "../ui/format";
import { SettingRow, settingDescriptionId } from "../ui/SettingRow";
import { PERCENT_INPUT_WIDTH } from "../ui/theme";

// A percentage as typed: digits, optionally with decimals.
const PERCENT_PATTERN = /^\d+(\.\d+)?$/;
const PERCENT_PLACES = 2; // a rate of 0.15 is 15%
const WITHHOLDING_INPUT_ID = "wallet-withholding-rate";

type Props = {
  wallet: WalletResponse | null; // the wallet whose settings to change; null when closed
  onClose: () => void;
  onSaved: (wallet: WalletResponse) => void;
};

export function WalletSettingsModal({ wallet, onClose, onSaved }: Props) {
  return (
    <Modal opened={wallet !== null} onClose={onClose} title="Wallet settings">
      {/* Keyed by wallet, so the form starts fresh for each one. */}
      {wallet && <SettingsForm key={wallet.id} wallet={wallet} onClose={onClose} onSaved={onSaved} />}
    </Modal>
  );
}

function SettingsForm({ wallet, onClose, onSaved }: { wallet: WalletResponse; onClose: () => void; onSaved: (wallet: WalletResponse) => void }) {
  const [percent, setPercent] = useState(shiftDecimal(wallet.withholding_rate, PERCENT_PLACES));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const typed = percent.trim().replace(",", ".");
  const invalid = typed !== "" && !PERCENT_PATTERN.test(typed);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (invalid) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const withholding_rate = shiftDecimal(typed || "0", -PERCENT_PLACES);
      const { data, error } = await updateWallet({ path: { wallet_id: wallet.id }, body: { withholding_rate } });
      if (data) {
        onClose();
        onSaved(data);
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
        <SettingRow
          id={WITHHOLDING_INPUT_ID}
          label="Dividend withholding tax"
          description="Kept back from each dividend before it is credited, e.g. 15% for US dividends under most tax treaties. Changing it recalculates all of this wallet’s dividends."
        >
          <TextInput
            id={WITHHOLDING_INPUT_ID}
            aria-describedby={settingDescriptionId(WITHHOLDING_INPUT_ID)}
            w={PERCENT_INPUT_WIDTH}
            inputMode="decimal"
            placeholder="0"
            data-autofocus
            rightSection="%"
            value={percent}
            onChange={(e) => setPercent(e.currentTarget.value)}
            error={invalid ? "Enter a number" : undefined}
          />
        </SettingRow>
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={saving} disabled={invalid}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

import { Alert, Button, Divider, Group, Modal, Stack, TagsInput, Text, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { setWalletRules, updateWallet, type WalletResponse } from "../api/generated";
import { shiftDecimal } from "../ui/format";
import { SettingRow, settingDescriptionId } from "../ui/SettingRow";
import { COUNT_INPUT_WIDTH, PERCENT_INPUT_WIDTH } from "../ui/theme";

// A percentage as typed: digits, optionally with decimals.
const PERCENT_PATTERN = /^\d+(\.\d+)?$/;
const PERCENT_PLACES = 2; // a rate of 0.15 is 15%
const WITHHOLDING_INPUT_ID = "wallet-withholding-rate";
const MAX_POSITION_INPUT_ID = "wallet-max-position";
const MIN_CASH_INPUT_ID = "wallet-min-cash";
const MAX_ORDERS_INPUT_ID = "wallet-max-orders";
const SYMBOLS_INPUT_ID = "wallet-allowed-symbols";
// A count as typed: whole digits only.
const COUNT_PATTERN = /^\d+$/;
const FULL_PERCENT = 100;

/** A percentage typed into a field, kept as text so it stays exact; `inRange` says whether a number is allowed. */
function usePercentField(ratio: string | null, inRange: (percent: number) => boolean, rangeMessage: string) {
  const [text, setText] = useState(ratio === null ? "" : shiftDecimal(ratio, PERCENT_PLACES));
  const typed = text.trim().replace(",", ".");
  const error = typed === "" ? null : !PERCENT_PATTERN.test(typed) ? "Enter a number" : !inRange(Number(typed)) ? rangeMessage : null;
  // As a ratio for the API (15 → 0.15), or null when left empty.
  const value = typed === "" ? null : shiftDecimal(typed, -PERCENT_PLACES);
  // Compared as numbers only to tell whether it changed, so 0.2 and 0.20 are the same.
  const changed = value === null || ratio === null ? value !== ratio : Number(value) !== Number(ratio);
  return { text, setText, error, value, changed };
}

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
  const withholding = usePercentField(wallet.withholding_rate, (percent) => percent < FULL_PERCENT, "Must be below 100%");
  const maxPosition = usePercentField(
    wallet.rules.max_position_weight,
    (percent) => percent > 0 && percent <= FULL_PERCENT,
    "Must be above 0% and at most 100%",
  );
  const minCash = usePercentField(wallet.rules.min_cash_weight, (percent) => percent < FULL_PERCENT, "Must be below 100%");
  const [symbols, setSymbols] = useState<string[]>(wallet.rules.allowed_symbols);
  const [maxOrders, setMaxOrders] = useState(wallet.rules.max_orders_per_month?.toString() ?? "");
  const typedOrders = maxOrders.trim();
  const ordersError = typedOrders === "" ? null : !COUNT_PATTERN.test(typedOrders) || Number(typedOrders) < 1 ? "Enter a whole number from 1" : null;
  const ordersValue = typedOrders === "" || ordersError ? null : Number(typedOrders);
  const rulesChanged =
    maxPosition.changed ||
    minCash.changed ||
    ordersValue !== wallet.rules.max_orders_per_month ||
    symbols.join() !== wallet.rules.allowed_symbols.join();
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const invalid = [withholding, maxPosition, minCash].some((field) => field.error !== null) || ordersError !== null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (invalid) {
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const path = { wallet_id: wallet.id };
      let saved = wallet;
      if (withholding.changed) {
        const { data, error } = await updateWallet({ path, body: { withholding_rate: withholding.value ?? "0" } });
        if (!data) {
          setError(apiErrorMessage(error));
          return;
        }
        saved = data;
      }
      if (rulesChanged) {
        const body = {
          max_position_weight: maxPosition.value,
          min_cash_weight: minCash.value,
          allowed_symbols: symbols,
          max_orders_per_month: ordersValue,
        };
        const { data, error } = await setWalletRules({ path, body });
        if (!data) {
          setError(apiErrorMessage(error));
          return;
        }
        saved = data;
      }
      onClose();
      onSaved(saved);
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setSaving(false);
    }
  }

  const percentInput = (id: string, field: ReturnType<typeof usePercentField>, placeholder: string, autofocus = false) => (
    <TextInput
      id={id}
      aria-describedby={settingDescriptionId(id)}
      w={PERCENT_INPUT_WIDTH}
      inputMode="decimal"
      placeholder={placeholder}
      data-autofocus={autofocus || undefined}
      rightSection="%"
      value={field.text}
      onChange={(e) => field.setText(e.currentTarget.value)}
      error={field.error}
    />
  );
  return (
    <form onSubmit={submit}>
      <Stack>
        <SettingRow
          id={WITHHOLDING_INPUT_ID}
          label="Dividend withholding tax"
          description="Kept back from each dividend before it is credited, e.g. 15% for US dividends under most tax treaties. Changing it recalculates all of this wallet’s dividends."
        >
          {percentInput(WITHHOLDING_INPUT_ID, withholding, "0", true)}
        </SettingRow>
        <Divider label="Rules for orders" labelPosition="left" />
        <Text size="xs" c="dimmed">
          Checked when an order is placed: one that would break a rule is refused, saying which. Open buys count too.
          Leave a rule empty for no limit.
        </Text>
        <SettingRow
          id={MAX_POSITION_INPUT_ID}
          label="Largest position"
          description="The most of the wallet’s value one holding may reach after a buy, e.g. 20% so no single company can sink it."
        >
          {percentInput(MAX_POSITION_INPUT_ID, maxPosition, "No limit")}
        </SettingRow>
        <SettingRow
          id={MIN_CASH_INPUT_ID}
          label="Cash to keep"
          description="The share of the wallet’s value to keep in cash after a buy, e.g. 5% to always have some ready."
        >
          {percentInput(MIN_CASH_INPUT_ID, minCash, "No limit")}
        </SettingRow>
        <SettingRow
          id={MAX_ORDERS_INPUT_ID}
          label="Orders a month"
          description="How many orders, buys and sells, the wallet may place in a calendar month; cancelled ones don’t count. Trading often costs returns."
        >
          <TextInput
            id={MAX_ORDERS_INPUT_ID}
            aria-describedby={settingDescriptionId(MAX_ORDERS_INPUT_ID)}
            w={COUNT_INPUT_WIDTH}
            inputMode="numeric"
            placeholder="No limit"
            value={maxOrders}
            onChange={(e) => setMaxOrders(e.currentTarget.value)}
            error={ordersError}
          />
        </SettingRow>
        <SettingRow
          id={SYMBOLS_INPUT_ID}
          label="Symbols it may buy"
          description="Only these can be bought; any can still be sold, to get out of a position. Leave empty for any symbol. Press Enter after each."
          wide
        >
          <TagsInput
            id={SYMBOLS_INPUT_ID}
            aria-describedby={settingDescriptionId(SYMBOLS_INPUT_ID)}
            placeholder="e.g. NVDA"
            value={symbols}
            onChange={(values) => setSymbols([...new Set(values.map((value) => value.trim().toUpperCase()).filter(Boolean))])}
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

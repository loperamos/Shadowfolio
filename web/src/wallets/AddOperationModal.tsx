import { Alert, Button, Group, Input, Modal, SegmentedControl, Select, SimpleGrid, Stack, TextInput } from "@mantine/core";
import { DateInput, TimePicker } from "@mantine/dates";
import { IconCalendar } from "@tabler/icons-react";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { Currency, deposit, OperationType, recordBuy, recordSell, type WalletResponse, withdraw } from "../api/generated";
import { DATE_INPUT_FORMAT, isInFuture, nowAsTimeValue, parseDateInput, todayAsInputValue, toUtcTimestamp } from "../ui/format";
import { DATE_INPUT_WIDTH, ICON_SIZE, TIME_INPUT_WIDTH } from "../ui/theme";

const OPERATION_LABELS: Record<OperationType, string> = {
  [OperationType.BUY]: "Buy",
  [OperationType.SELL]: "Sell",
  [OperationType.DEPOSIT]: "Deposit",
  [OperationType.WITHDRAWAL]: "Withdrawal",
};
const OPERATION_OPTIONS = Object.entries(OPERATION_LABELS).map(([value, label]) => ({ value, label }));
const CURRENCIES = Object.values(Currency);
// The MVP covers US stocks and ETFs, which are priced in dollars.
const DEFAULT_PRICE_CURRENCY = Currency.USD;

type Props = {
  wallet: WalletResponse;
  opened: boolean;
  onClose: () => void;
  onAdded: () => void;
};

/** Record something that already happened in the wallet: a trade or a cash movement, at its real date. */
export function AddOperationModal({ wallet, opened, onClose, onAdded }: Props) {
  return (
    <Modal opened={opened} onClose={onClose} title="Add operation" size="lg">
      {/* Rendered only while open, so the form starts empty each time. */}
      {opened && <AddOperationForm wallet={wallet} onClose={onClose} onAdded={onAdded} />}
    </Modal>
  );
}

function AddOperationForm({ wallet, onClose, onAdded }: Omit<Props, "opened">) {
  const [type, setType] = useState<OperationType>(OperationType.BUY);
  // Amounts are kept as text and sent as strings, so they stay exact (never through a float).
  // Local date and time, entered separately as on broker statements; they start at now, the most common case.
  const [date, setDate] = useState<string | null>(todayAsInputValue); // "2024-06-24"
  const [time, setTime] = useState(nowAsTimeValue); // "16:26"
  const [amount, setAmount] = useState("");
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [priceCurrency, setPriceCurrency] = useState<Currency>(DEFAULT_PRICE_CURRENCY);
  const [settledAmount, setSettledAmount] = useState("");
  const [fees, setFees] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const isTrade = type === OperationType.BUY || type === OperationType.SELL;
  // A trade priced in another currency needs the amount the broker settled in the wallet's currency.
  const needsSettledAmount = isTrade && priceCurrency !== wallet.currency;

  async function send() {
    const path = { wallet_id: wallet.id };
    const timestamp = toUtcTimestamp(date!, time);
    if (!isTrade) {
      const body = { amount, timestamp };
      return type === OperationType.DEPOSIT ? deposit({ path, body }) : withdraw({ path, body });
    }
    const body = {
      symbol: symbol.trim().toUpperCase(),
      quantity,
      price,
      price_currency: priceCurrency,
      timestamp,
      settled_amount: needsSettledAmount ? settledAmount : null,
      ...(fees.trim() ? { fees } : {}),
    };
    return type === OperationType.BUY ? recordBuy({ path, body }) : recordSell({ path, body });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!date || !time) {
      setError("Enter the date and time of the operation.");
      return;
    }
    if (isInFuture(date, time)) {
      return; // the time field already shows why
    }
    setSaving(true);
    setError(null);
    try {
      const { data, error } = await send();
      if (data) {
        onClose();
        onAdded();
      } else {
        setError(apiErrorMessage(error));
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setSaving(false);
    }
  }

  const today = todayAsInputValue();
  function setToNow() {
    setDate(todayAsInputValue());
    setTime(nowAsTimeValue());
  }

  const timeInFuture = date !== null && time !== "" && isInFuture(date, time);
  // One row under one label: two compact fields and a shortcut back to the present.
  const dateAndTime = (
    <Input.Wrapper label="Date and time" required error={timeInFuture ? "Can't be later than now" : undefined}>
      <Group gap="xs" wrap="nowrap">
        <DateInput
          aria-label="Date"
          w={DATE_INPUT_WIDTH}
          placeholder={DATE_INPUT_FORMAT}
          valueFormat={DATE_INPUT_FORMAT}
          dateParser={parseDateInput}
          leftSection={<IconCalendar size={ICON_SIZE} />}
          // Operations record what already happened.
          maxDate={today}
          value={date}
          onChange={setDate}
        />
        <TimePicker
          aria-label="Time"
          w={TIME_INPUT_WIDTH}
          withDropdown
          // Validated rather than limited: Mantine would silently replace a later time with the limit.
          error={timeInFuture}
          value={time}
          onChange={setTime}
        />
        <Button variant="default" onClick={setToNow}>
          Now
        </Button>
      </Group>
    </Input.Wrapper>
  );

  return (
    <form onSubmit={submit}>
      <Stack>
        <SegmentedControl fullWidth data={OPERATION_OPTIONS} value={type} onChange={(value) => setType(value as OperationType)} />

        {dateAndTime}

        {isTrade ? (
          <SimpleGrid cols={2}>
            <TextInput label="Symbol" placeholder="NVDA" required value={symbol} onChange={(e) => setSymbol(e.currentTarget.value)} />
            <TextInput label="Quantity" inputMode="decimal" required value={quantity} onChange={(e) => setQuantity(e.currentTarget.value)} />
            <TextInput label="Price per share" inputMode="decimal" required value={price} onChange={(e) => setPrice(e.currentTarget.value)} />
            <Select
              label="Price currency"
              data={CURRENCIES}
              allowDeselect={false}
              value={priceCurrency}
              onChange={(value) => value && setPriceCurrency(value as Currency)}
            />
            <TextInput label={`Fees in ${wallet.currency}`} placeholder="0" inputMode="decimal" value={fees} onChange={(e) => setFees(e.currentTarget.value)} />
          </SimpleGrid>
        ) : (
          <SimpleGrid cols={2}>
            <TextInput
              label={`Amount in ${wallet.currency}`}
              inputMode="decimal"
              required
              value={amount}
              onChange={(e) => setAmount(e.currentTarget.value)}
            />
          </SimpleGrid>
        )}

        {needsSettledAmount && (
          <TextInput
            label={`Amount in ${wallet.currency}, before fees`}
            description={`What ${type === OperationType.BUY ? "left" : "entered"} your account in ${wallet.currency}, as on your broker statement`}
            inputMode="decimal"
            required
            value={settledAmount}
            onChange={(e) => setSettledAmount(e.currentTarget.value)}
          />
        )}

        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            Add {OPERATION_LABELS[type].toLowerCase()}
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

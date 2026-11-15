import { Alert, Button, Group, Modal, SegmentedControl, SimpleGrid, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { type FormEvent, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { OrderSide, placeOrder, type WalletResponse } from "../api/generated";

// Market orders fill at the next price; limit orders only at their limit price or better.
enum OrderKind {
  MARKET = "market",
  LIMIT = "limit",
}

const SIDE_OPTIONS = [
  { value: OrderSide.BUY, label: "Buy" },
  { value: OrderSide.SELL, label: "Sell" },
];
const KIND_OPTIONS = [
  { value: OrderKind.MARKET, label: "At market" },
  { value: OrderKind.LIMIT, label: "With a limit" },
];

type Props = {
  wallet: WalletResponse;
  opened: boolean;
  onClose: () => void;
  onPlaced: () => void;
};

/** Place an order now (unlike a past operation): it fills later, at the first price after it, as the market allows. */
export function PlaceOrderModal({ wallet, opened, onClose, onPlaced }: Props) {
  return (
    <Modal opened={opened} onClose={onClose} title="Place order" size="lg">
      {/* Rendered only while open, so the form starts empty each time. */}
      {opened && <OrderForm wallet={wallet} onClose={onClose} onPlaced={onPlaced} />}
    </Modal>
  );
}

function OrderForm({ wallet, onClose, onPlaced }: Omit<Props, "opened">) {
  const [side, setSide] = useState<OrderSide>(OrderSide.BUY);
  const [kind, setKind] = useState(OrderKind.MARKET);
  // Amounts are kept as text and sent as strings, so they stay exact (never through a float).
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [limitPrice, setLimitPrice] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [placing, setPlacing] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setPlacing(true);
    setError(null);
    try {
      const body = { side, symbol: symbol.trim().toUpperCase(), quantity, reason, limit_price: kind === OrderKind.LIMIT ? limitPrice : null };
      const { data, error } = await placeOrder({ path: { wallet_id: wallet.id }, body });
      if (data) {
        onClose();
        onPlaced();
      } else {
        setError(apiErrorMessage(error));
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setPlacing(false);
    }
  }

  const sideLabel = side === OrderSide.BUY ? "buy" : "sell";
  return (
    <form onSubmit={submit}>
      <Stack>
        <SegmentedControl fullWidth aria-label="Buy or sell" data={SIDE_OPTIONS} value={side} onChange={(value) => setSide(value as OrderSide)} />
        <SimpleGrid cols={2}>
          <TextInput label="Symbol" placeholder="NVDA" required data-autofocus value={symbol} onChange={(e) => setSymbol(e.currentTarget.value)} />
          <TextInput label="Quantity" inputMode="decimal" required value={quantity} onChange={(e) => setQuantity(e.currentTarget.value)} />
        </SimpleGrid>
        <SegmentedControl fullWidth aria-label="Price" data={KIND_OPTIONS} value={kind} onChange={(value) => setKind(value as OrderKind)} />
        {kind === OrderKind.LIMIT && (
          <TextInput
            label="Limit price per share"
            description={side === OrderSide.BUY ? "The most to pay, in the stock's currency (USD for US stocks)" : "The least to take, in the stock's currency (USD for US stocks)"}
            inputMode="decimal"
            required
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.currentTarget.value)}
          />
        )}
        <Textarea label="Why" description="Optional; kept with the order as a decision log" autosize minRows={2} value={reason} onChange={(e) => setReason(e.currentTarget.value)} />
        {/* How it fills, said before placing it, as the fill rules are part of the product. */}
        <Text c="dimmed" size="sm">
          {kind === OrderKind.MARKET
            ? `Fills at the first price after you place it; while the market is closed, at the next open. Cash and shares are checked when it fills.`
            : `Fills on the first minute after you place it that reaches your limit, at the limit or better; until then it stays open. Cash and shares are checked when it fills.`}
        </Text>
        {error && <Alert color="red">{error}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={placing}>
            Place {sideLabel} order
          </Button>
        </Group>
      </Stack>
    </form>
  );
}

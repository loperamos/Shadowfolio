import { Alert, Button, Group, Modal, SegmentedControl, SimpleGrid, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { type FormEvent, useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { estimateOrder, type OrderEstimateResponse, OrderSide, placeOrder, type WalletResponse } from "../api/generated";
import { shortDecimal } from "../ui/format";
import { Money } from "../ui/Money";
import type { ValuationState } from "./useWalletValuation";

// Market orders fill at the next price; limit orders only at their limit price or better.
enum OrderKind {
  MARKET = "market",
  LIMIT = "limit",
}

// How long typing must pause before the order is estimated, so each keystroke does not ask for a price.
const ESTIMATE_DELAY_MS = 400;
// Exchange rates are shown to this many decimals; the estimate uses the exact rate.
const RATE_DECIMALS = 4;

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
  valuation: ValuationState;
  opened: boolean;
  onClose: () => void;
  onPlaced: () => void;
};

/** Place an order now (unlike a past operation): it fills later, at the first price after it, as the market allows. */
export function PlaceOrderModal({ wallet, valuation, opened, onClose, onPlaced }: Props) {
  return (
    <Modal opened={opened} onClose={onClose} title="Place order" size="lg">
      {/* Rendered only while open, so the form starts empty each time. */}
      {opened && <OrderForm wallet={wallet} valuation={valuation} onClose={onClose} onPlaced={onPlaced} />}
    </Modal>
  );
}

function OrderForm({ wallet, valuation, onClose, onPlaced }: Omit<Props, "opened">) {
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
        {side === OrderSide.BUY && valuation.status === "loaded" && valuation.valuation.buying_power != null && (
          <Text size="sm">
            Buying power: <Money amount={valuation.valuation.buying_power} currency={valuation.valuation.currency} fw={600} />, the cash
            not yet committed to open buys.
          </Text>
        )}
        <EstimatedAmount
          walletId={wallet.id}
          walletCurrency={wallet.currency}
          side={side}
          symbol={symbol.trim()}
          quantity={quantity.trim()}
          limitPrice={kind === OrderKind.LIMIT ? limitPrice.trim() : null}
          buyingPower={valuation.status === "loaded" ? valuation.valuation.buying_power : null}
        />
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

type EstimateState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "loaded"; estimate: OrderEstimateResponse };

type EstimateProps = {
  walletId: string;
  walletCurrency: string;
  side: OrderSide;
  symbol: string;
  quantity: string;
  limitPrice: string | null; // null for a market order
  buyingPower: string | null | undefined;
};

/**
 * What the order would come to in the wallet's currency, once it is filled in: at its limit, or at the latest price for
 * a market order. A buy above the buying power is warned about, not refused: the cash is checked when it fills.
 */
function EstimatedAmount({ walletId, walletCurrency, side, symbol, quantity, limitPrice, buyingPower }: EstimateProps) {
  const [request] = useDebouncedValue({ side, symbol, quantity, limitPrice }, ESTIMATE_DELAY_MS);
  const [state, setState] = useState<EstimateState>({ status: "idle" });
  const { side: askedSide, symbol: askedSymbol, quantity: askedQuantity, limitPrice: askedLimit } = request;

  useEffect(() => {
    if (!askedSymbol || !askedQuantity || askedLimit === "") {
      setState({ status: "idle" });
      return;
    }
    let current = true; // ignore answers to an order since changed
    setState({ status: "loading" });
    const query = { side: askedSide, symbol: askedSymbol, quantity: askedQuantity, limit_price: askedLimit };
    estimateOrder({ path: { wallet_id: walletId }, query })
      .then(({ data, error }) => {
        if (current) {
          setState(data ? { status: "loaded", estimate: data } : { status: "error", message: apiErrorMessage(error) });
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [walletId, askedSide, askedSymbol, askedQuantity, askedLimit]);

  switch (state.status) {
    case "idle":
      return null;
    case "loading":
      return (
        <Text c="dimmed" size="sm">
          Estimating…
        </Text>
      );
    case "error":
      return (
        <Text c="dimmed" size="sm">
          No estimate: {state.message}
        </Text>
      );
    case "loaded": {
      const { price, currency, fx_rate, amount } = state.estimate;
      const fx = fx_rate ? ` at ${shortDecimal(fx_rate.rate, RATE_DECIMALS)}` : "";
      const overBuyingPower = side === OrderSide.BUY && buyingPower != null && Number(amount) > Number(buyingPower);
      return (
        <>
          <Text size="sm">
            {side === OrderSide.BUY ? "Costs" : "Brings in"} about <Money amount={amount} currency={walletCurrency} fw={600} /> (
            {quantity} × <Money amount={price} currency={currency} />
            {fx}).
          </Text>
          {overBuyingPower && (
            <Alert color="yellow">
              That is more than the buying power. It will be rejected when it fills, unless cash comes in or other buys are
              cancelled first.
            </Alert>
          )}
        </>
      );
    }
  }
}

import { Alert, Badge, Button, Group, Loader, Modal, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";
import {
  cancelOrder,
  orderOutcomes,
  type OrderOutcomeResponse,
  type OrderResponse,
  OrderSide,
  OrderStatus,
  type WalletResponse,
} from "../api/generated";
import { ReturnText } from "../ui/GainText";
import { InfoTip } from "../ui/InfoTip";
import { Money } from "../ui/Money";
import { formatDateTime } from "../ui/format";
import { TABLE_MIN_WIDTH, TOOLTIP_WIDTH } from "../ui/theme";

const STATUS_BADGES: Record<OrderStatus, { label: string; color: string }> = {
  [OrderStatus.OPEN]: { label: "Open", color: "blue" },
  [OrderStatus.FILLED]: { label: "Filled", color: "teal" },
  [OrderStatus.CANCELLED]: { label: "Cancelled", color: "gray" },
  [OrderStatus.REJECTED]: { label: "Rejected", color: "red" },
};

type Props = {
  wallet: WalletResponse;
  orders: OrderResponse[];
  benchmarkSymbol: string | null; // the one chosen on the page; null for the default
  refreshKey: number; // changes when the wallet's history does, to load the outcomes again
  onChanged: () => void;
};

type OutcomesState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; byOrder: Map<string, OrderOutcomeResponse> };

/** The wallet's orders, newest first: what was asked, its status, when and at what price it filled, and since. */
export function WalletOrders({ wallet, orders, benchmarkSymbol, refreshKey, onChanged }: Props) {
  const [toCancel, setToCancel] = useState<OrderResponse | null>(null);
  const outcomes = useOrderOutcomes(wallet.id, benchmarkSymbol, refreshKey);
  return (
    <div>
      <Title order={2} mb="sm">
        Orders
      </Title>
      {orders.length === 0 ? (
        <Text c="dimmed">No orders yet. Use “Place order” to buy or sell now, at the next market price.</Text>
      ) : (
        <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Placed</Table.Th>
                <Table.Th>Order</Table.Th>
                <Table.Th>Status</Table.Th>
                <Table.Th>Filled</Table.Th>
                <Table.Th>
                  <Group gap={4} wrap="nowrap">
                    Since
                    <InfoTip topic="since">
                      How the symbol moved from the fill price to its latest, with the benchmark from the same moment
                      below. A buy did well if it rose more than the benchmark; a sell, if it rose less (or fell), as
                      the money was out of it.
                    </InfoTip>
                  </Group>
                </Table.Th>
                <Table.Th>Why</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {[...orders].reverse().map((order) => (
                <Table.Tr key={order.id}>
                  <Table.Td>{formatDateTime(order.placed_at)}</Table.Td>
                  <Table.Td>{describe(order)}</Table.Td>
                  <Table.Td>
                    <StatusBadge order={order} />
                  </Table.Td>
                  <Table.Td>
                    {order.status === OrderStatus.FILLED && order.price != null && order.price_currency && order.closed_at && (
                      <Group gap={6} wrap="nowrap">
                        <Money amount={order.price} currency={order.price_currency} />
                        <Text c="dimmed" size="sm">
                          {formatDateTime(order.closed_at)}
                        </Text>
                      </Group>
                    )}
                  </Table.Td>
                  <Table.Td>{order.status === OrderStatus.FILLED && <Outcome state={outcomes} orderId={order.id} />}</Table.Td>
                  <Table.Td>
                    <Text size="sm">{order.reason}</Text>
                  </Table.Td>
                  <Table.Td ta="right">
                    {order.status === OrderStatus.OPEN && (
                      <Button size="xs" variant="subtle" color="red" onClick={() => setToCancel(order)}>
                        Cancel
                      </Button>
                    )}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      {outcomes.status === "error" && (
        <Text c="dimmed" size="sm" mt="xs">
          How the orders turned out is unavailable: {outcomes.message}
        </Text>
      )}
      <CancelOrderModal wallet={wallet} order={toCancel} onClose={() => setToCancel(null)} onCancelled={onChanged} />
    </div>
  );
}

/** How each filled order turned out, against `benchmarkSymbol` (the default when null), loaded apart from the orders. */
function useOrderOutcomes(walletId: string, benchmarkSymbol: string | null, refreshKey: number): OutcomesState {
  const [state, setState] = useState<OutcomesState>({ status: "loading" });
  useEffect(() => {
    let current = true; // ignore answers for a wallet or benchmark since changed
    setState({ status: "loading" });
    orderOutcomes({ path: { wallet_id: walletId }, query: benchmarkSymbol ? { benchmark: benchmarkSymbol } : undefined })
      .then(({ data, error }) => {
        if (current) {
          setState(
            data
              ? { status: "loaded", byOrder: new Map(data.map((outcome) => [outcome.order_id, outcome])) }
              : { status: "error", message: apiErrorMessage(error) },
          );
        }
      })
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, [walletId, benchmarkSymbol, refreshKey]);
  return state;
}

/** A filled order's return since, with the benchmark's below; a dash when a price is missing. */
function Outcome({ state, orderId }: { state: OutcomesState; orderId: string }) {
  if (state.status === "loading") {
    return <Loader size="xs" />;
  }
  const outcome = state.status === "loaded" ? state.byOrder.get(orderId) : undefined;
  if (!outcome || outcome.return_percent == null) {
    return <Text c="dimmed">—</Text>;
  }
  return (
    <>
      <ReturnText percent={outcome.return_percent} size="sm" />
      <Text c="dimmed" size="xs">
        {outcome.benchmark_symbol}{" "}
        {outcome.benchmark_return_percent == null ? "—" : <ReturnText percent={outcome.benchmark_return_percent} span inherit />}
      </Text>
    </>
  );
}

/** "Buy 8 NVDA at market", "Sell 2 NVDA, limit 130". */
function describe(order: OrderResponse): string {
  const side = order.side === OrderSide.BUY ? "Buy" : "Sell";
  return `${side} ${order.quantity} ${order.symbol}${order.limit_price != null ? `, limit ${order.limit_price}` : " at market"}`;
}

/** The order's status; a rejected one says why when pointed at. */
function StatusBadge({ order }: { order: OrderResponse }) {
  const { label, color } = STATUS_BADGES[order.status];
  const badge = (
    <Badge color={color} variant="light">
      {label}
    </Badge>
  );
  return order.rejection ? (
    <Tooltip label={order.rejection} multiline w={TOOLTIP_WIDTH}>
      {badge}
    </Tooltip>
  ) : (
    badge
  );
}

/** Asks before cancelling: a cancelled order cannot be reopened. */
function CancelOrderModal({ wallet, order, onClose, onCancelled }: { wallet: WalletResponse; order: OrderResponse | null; onClose: () => void; onCancelled: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  function close() {
    setError(null);
    onClose();
  }

  async function confirm() {
    if (!order) {
      return;
    }
    setCancelling(true);
    setError(null);
    try {
      const { data, error } = await cancelOrder({ path: { wallet_id: wallet.id, order_id: order.id } });
      if (data) {
        close();
        onCancelled();
      } else {
        setError(apiErrorMessage(error));
      }
    } catch {
      setError("Could not reach the backend.");
    } finally {
      setCancelling(false);
    }
  }

  return (
    <Modal opened={order !== null} onClose={close} title="Cancel order?">
      {order && (
        <Stack>
          <Text>
            “{describe(order)}”, placed {formatDateTime(order.placed_at)}, will not fill. A cancelled order cannot be reopened; you can place a new one.
          </Text>
          {error && <Alert color="red">{error}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Keep it
            </Button>
            <Button color="red" loading={cancelling} onClick={confirm}>
              Cancel order
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

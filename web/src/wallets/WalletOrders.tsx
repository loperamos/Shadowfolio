import { Alert, Badge, Button, Group, Modal, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { useState } from "react";

import { apiErrorMessage } from "../api/errors";
import { cancelOrder, type OrderResponse, OrderSide, OrderStatus, type WalletResponse } from "../api/generated";
import { Money } from "../ui/Money";
import { formatDateTime } from "../ui/format";
import { TABLE_MIN_WIDTH, TOOLTIP_WIDTH } from "../ui/theme";

const STATUS_BADGES: Record<OrderStatus, { label: string; color: string }> = {
  [OrderStatus.OPEN]: { label: "Open", color: "blue" },
  [OrderStatus.FILLED]: { label: "Filled", color: "teal" },
  [OrderStatus.CANCELLED]: { label: "Cancelled", color: "gray" },
  [OrderStatus.REJECTED]: { label: "Rejected", color: "red" },
};

type Props = { wallet: WalletResponse; orders: OrderResponse[]; onChanged: () => void };

/** The wallet's orders, newest first: what was asked, its status, and when and at what price it filled. */
export function WalletOrders({ wallet, orders, onChanged }: Props) {
  const [toCancel, setToCancel] = useState<OrderResponse | null>(null);
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
      <CancelOrderModal wallet={wallet} order={toCancel} onClose={() => setToCancel(null)} onCancelled={onChanged} />
    </div>
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

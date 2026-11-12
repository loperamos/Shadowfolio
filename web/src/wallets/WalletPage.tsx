import { Alert, Anchor, Breadcrumbs, Group, Loader, Stack, Table, Text, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { apiErrorMessage } from "../api/errors";
import { getWallet, listOperations, type OperationResponse, renameWallet, type WalletResponse } from "../api/generated";
import { walletPath, WALLETS_PATH } from "../routes";
import { EditableTitle } from "../ui/EditableTitle";
import { DeleteWalletsModal } from "./DeleteWalletsModal";
import { DuplicateWalletModal } from "./DuplicateWalletModal";
import { WalletActionsMenu } from "./WalletActionsMenu";

const NOT_FOUND_STATUS = 404;
const DATE_FORMAT = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

type Loaded = { wallet: WalletResponse; operations: OperationResponse[] };
type State = { status: "loading" } | { status: "not-found" } | { status: "error"; message: string } | ({ status: "loaded" } & Loaded);

/** One wallet: its cash, holdings and history. */
export function WalletPage() {
  const { walletId = "" } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState<State>({ status: "loading" });
  const [editingName, setEditingName] = useState(false);
  const [toDuplicate, setToDuplicate] = useState<WalletResponse | null>(null);
  const [toDelete, setToDelete] = useState<WalletResponse[]>([]);

  useEffect(() => {
    setState({ status: "loading" });
    const path = { wallet_id: walletId };
    Promise.all([getWallet({ path }), listOperations({ path })])
      .then(([wallet, operations]) => {
        if (wallet.response?.status === NOT_FOUND_STATUS) {
          setState({ status: "not-found" });
        } else if (wallet.data && operations.data) {
          setState({ status: "loaded", wallet: wallet.data, operations: operations.data });
        } else {
          setState({ status: "error", message: "Could not load the wallet." });
        }
      })
      .catch(() => setState({ status: "error", message: "Could not reach the backend." }));
  }, [walletId]);

  const breadcrumbs = (current: string) => (
    <Breadcrumbs mb="md">
      <Anchor component={Link} to={WALLETS_PATH}>
        Wallets
      </Anchor>
      <Text>{current}</Text>
    </Breadcrumbs>
  );

  async function rename(name: string): Promise<string | null> {
    try {
      const { data, error } = await renameWallet({ path: { wallet_id: walletId }, body: { name } });
      if (!data) {
        return apiErrorMessage(error);
      }
      setState((current) => (current.status === "loaded" ? { ...current, wallet: data } : current));
      return null;
    } catch {
      return "Could not reach the backend.";
    }
  }

  switch (state.status) {
    case "loading":
      return <Loader />;
    case "not-found":
      return (
        <>
          {breadcrumbs("Not found")}
          <Alert color="yellow" title="Wallet not found">
            It may have been deleted.{" "}
            <Anchor component={Link} to={WALLETS_PATH}>
              Back to your wallets
            </Anchor>
          </Alert>
        </>
      );
    case "error":
      return <Alert color="red">{state.message}</Alert>;
    case "loaded":
      return (
        <>
          {breadcrumbs(state.wallet.name)}
          <Group justify="space-between" mb="lg">
            <EditableTitle value={state.wallet.name} editing={editingName} onEditingChange={setEditingName} onSave={rename} label="Wallet name" />
            <WalletActionsMenu wallet={state.wallet} onRename={() => setEditingName(true)} onDuplicate={setToDuplicate} onDelete={setToDelete} />
          </Group>
          <WalletDetails wallet={state.wallet} operations={state.operations} />
          {/* Duplicating opens the copy; deleting goes back to the list. */}
          <DuplicateWalletModal wallet={toDuplicate} onClose={() => setToDuplicate(null)} onDuplicated={(copy) => navigate(walletPath(copy.id))} />
          <DeleteWalletsModal wallets={toDelete} onClose={() => setToDelete([])} onDeleted={(allDeleted) => allDeleted && navigate(WALLETS_PATH)} />
        </>
      );
  }
}

function WalletDetails({ wallet, operations }: Loaded) {
  const holdings = Object.entries(wallet.holdings);
  return (
    <Stack gap="xl">
      <div>
        <Text c="dimmed" size="sm">
          Cash
        </Text>
        <Text size="xl" fw={600}>
          {wallet.cash} {wallet.currency}
        </Text>
      </div>

      <div>
        <Title order={2} mb="sm">
          Holdings
        </Title>
        {holdings.length === 0 ? (
          <Text c="dimmed">No holdings.</Text>
        ) : (
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Symbol</Table.Th>
                <Table.Th ta="right">Shares</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {holdings.map(([symbol, quantity]) => (
                <Table.Tr key={symbol}>
                  <Table.Td>{symbol}</Table.Td>
                  <Table.Td ta="right">{quantity}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </div>

      <div>
        <Title order={2} mb="sm">
          Operations
        </Title>
        {operations.length === 0 ? (
          <Text c="dimmed">No operations yet.</Text>
        ) : (
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Date</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Symbol</Table.Th>
                <Table.Th ta="right">Quantity</Table.Th>
                <Table.Th ta="right">Price</Table.Th>
                <Table.Th ta="right">Amount</Table.Th>
                <Table.Th ta="right">Fees</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {/* Newest first, as in a statement. */}
              {[...operations].reverse().map((op) => (
                <Table.Tr key={op.id}>
                  <Table.Td>{DATE_FORMAT.format(new Date(op.timestamp))}</Table.Td>
                  <Table.Td tt="capitalize">{op.type}</Table.Td>
                  <Table.Td>{op.symbol ?? ""}</Table.Td>
                  <Table.Td ta="right">{op.quantity ?? ""}</Table.Td>
                  <Table.Td ta="right">{op.price != null ? `${op.price} ${op.price_currency}` : ""}</Table.Td>
                  <Table.Td ta="right">
                    {op.amount} {wallet.currency}
                  </Table.Td>
                  <Table.Td ta="right">{op.fees !== "0" ? `${op.fees} ${wallet.currency}` : ""}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </div>
    </Stack>
  );
}

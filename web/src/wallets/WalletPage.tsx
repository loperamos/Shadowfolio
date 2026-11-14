import { Alert, Anchor, Breadcrumbs, Button, Group, Loader, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { IconPlus } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { apiErrorMessage } from "../api/errors";
import { getWallet, listOperations, type OperationResponse, OperationType, PriceSource, updateWallet, type WalletResponse } from "../api/generated";
import { walletPath, WALLETS_PATH } from "../routes";
import { EditableTitle } from "../ui/EditableTitle";
import { GainText } from "../ui/GainText";
import { Money } from "../ui/Money";
import { formatDate, formatDateTime, shortDecimal } from "../ui/format";
import { ICON_SIZE, TABLE_MIN_WIDTH } from "../ui/theme";
import { DeleteOperationModal } from "./DeleteOperationModal";
import { OperationActionsMenu } from "./OperationActionsMenu";
import { isEditable, OperationModal } from "./OperationModal";
import { DeleteWalletsModal } from "./DeleteWalletsModal";
import { DuplicateWalletModal } from "./DuplicateWalletModal";
import { type ValuationState, useWalletValuation } from "./useWalletValuation";
import { AutomaticBadge, HindsightBadge, MarketPriceBadge } from "./HindsightBadges";
import { SplitsCheckNotice } from "./SplitsCheckNotice";
import { UncreditedDividendsNotice } from "./UncreditedDividendsNotice";
import { WalletActionsMenu } from "./WalletActionsMenu";
import { WalletSettingsModal } from "./WalletSettingsModal";
import { WalletValueChart } from "./WalletValueChart";
import { WalletDayChange, WalletGain, WalletValue } from "./WalletValue";

const NOT_FOUND_STATUS = 404;
// Exchange rates are shown to this many decimals in tooltips; the valuation uses the exact rate.
const RATE_DECIMALS = 4;

type Loaded = { wallet: WalletResponse; operations: OperationResponse[] };
type State = { status: "loading" } | { status: "not-found" } | { status: "error"; message: string } | ({ status: "loaded" } & Loaded);

/** One wallet: its cash, holdings and history. */
export function WalletPage() {
  const { walletId = "" } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState<State>({ status: "loading" });
  const [editingName, setEditingName] = useState(false);
  // The operation dialog: closed, adding a new operation, or editing an existing one.
  const [operationDialog, setOperationDialog] = useState<{ operation: OperationResponse | null } | null>(null);
  const [operationToDelete, setOperationToDelete] = useState<OperationResponse | null>(null);
  // Bumped after the wallet's history changes, to load it (and its value) again.
  const [version, setVersion] = useState(0);
  const [toDuplicate, setToDuplicate] = useState<WalletResponse | null>(null);
  const [toConfigure, setToConfigure] = useState<WalletResponse | null>(null);
  const [toDelete, setToDelete] = useState<WalletResponse[]>([]);

  useEffect(() => {
    // Keep showing the wallet while it reloads; show the loader only when opening another one.
    setState((current) => (current.status === "loaded" && current.wallet.id === walletId ? current : { status: "loading" }));
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
  }, [walletId, version]);

  const breadcrumbs = (current: string) => (
    <Breadcrumbs mb="md">
      <Anchor component={Link} to={WALLETS_PATH}>
        Wallets
      </Anchor>
      <Text>{current}</Text>
    </Breadcrumbs>
  );

  function reload() {
    setVersion((v) => v + 1);
  }

  async function rename(name: string): Promise<string | null> {
    try {
      const { data, error } = await updateWallet({ path: { wallet_id: walletId }, body: { name } });
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
            <Group gap="sm" wrap="nowrap">
              <EditableTitle value={state.wallet.name} editing={editingName} onEditingChange={setEditingName} onSave={rename} label="Wallet name" />
              {state.wallet.hindsight && <HindsightBadge />}
            </Group>
            <Group gap="xs" wrap="nowrap">
              <Button leftSection={<IconPlus size={ICON_SIZE} />} onClick={() => setOperationDialog({ operation: null })}>
                Add operation
              </Button>
              <WalletActionsMenu wallet={state.wallet} onRename={() => setEditingName(true)} onSettings={setToConfigure} onDuplicate={setToDuplicate} onDelete={setToDelete} />
            </Group>
          </Group>
          <SplitsCheckNotice wallet={state.wallet} />
          <UncreditedDividendsNotice wallet={state.wallet} />
          <WalletDetails
            wallet={state.wallet}
            operations={state.operations}
            version={version}
            onEditOperation={(operation) => setOperationDialog({ operation })}
            onDeleteOperation={setOperationToDelete}
          />
          <OperationModal
            wallet={state.wallet}
            opened={operationDialog !== null}
            operation={operationDialog?.operation ?? null}
            onClose={() => setOperationDialog(null)}
            onSaved={reload}
          />
          <DeleteOperationModal wallet={state.wallet} operation={operationToDelete} onClose={() => setOperationToDelete(null)} onDeleted={reload} />
          {/* Duplicating opens the copy; deleting goes back to the list. */}
          <WalletSettingsModal wallet={toConfigure} onClose={() => setToConfigure(null)} onSaved={reload} />
          <DuplicateWalletModal wallet={toDuplicate} onClose={() => setToDuplicate(null)} onDuplicated={(copy) => navigate(walletPath(copy.id))} />
          <DeleteWalletsModal wallets={toDelete} onClose={() => setToDelete([])} onDeleted={(allDeleted) => allDeleted && navigate(WALLETS_PATH)} />
        </>
      );
  }
}

type DetailsProps = Loaded & {
  version: number;
  onEditOperation: (operation: OperationResponse) => void;
  onDeleteOperation: (operation: OperationResponse) => void;
};

function WalletDetails({ wallet, operations, version, onEditOperation, onDeleteOperation }: DetailsProps) {
  // Splits that changed nothing (no shares held on their date) are left out: they only add noise.
  const shownOperations = operations.filter((op) => op.had_effect !== false);
  const holdings = Object.entries(wallet.holdings);
  const valuation = useWalletValuation(wallet.id, version);
  return (
    <Stack gap="xl">
      <Group gap="xl">
        <div>
          <Text c="dimmed" size="sm">
            Cash
          </Text>
          <Money amount={wallet.cash} currency={wallet.currency} size="xl" fw={600} />
        </div>
        <div>
          <Text c="dimmed" size="sm">
            Value
          </Text>
          <WalletValue state={valuation} size="xl" fw={600} />
        </div>
        <div>
          <Text c="dimmed" size="sm">
            Today
          </Text>
          <WalletDayChange state={valuation} size="xl" fw={600} />
        </div>
        <div>
          <Text c="dimmed" size="sm">
            Unrealized gain
          </Text>
          <WalletGain state={valuation} size="xl" fw={600} />
        </div>
        <div>
          <Text c="dimmed" size="sm">
            Realized gain
          </Text>
          <GainText amount={wallet.realized_gain} currency={wallet.currency} size="xl" fw={600} />
        </div>
      </Group>
      {valuation.status === "error" && (
        <Alert color="yellow" title="Value unavailable">
          {valuation.message}
        </Alert>
      )}

      <WalletValueChart walletId={wallet.id} currency={wallet.currency} refreshKey={version} />

      <div>
        <Title order={2} mb="sm">
          Holdings
        </Title>
        {holdings.length === 0 ? (
          <Text c="dimmed">No holdings.</Text>
        ) : (
          <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Symbol</Table.Th>
                <Table.Th ta="right">Shares</Table.Th>
                <Table.Th ta="right">Cost</Table.Th>
                <Table.Th ta="right">Price</Table.Th>
                <Table.Th ta="right">Value</Table.Th>
                <Table.Th ta="right">Today</Table.Th>
                <Table.Th ta="right">Gain</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {holdings.map(([symbol, quantity]) => (
                <Table.Tr key={symbol}>
                  <Table.Td>{symbol}</Table.Td>
                  <Table.Td ta="right">{quantity}</Table.Td>
                  <Table.Td ta="right">
                    <Money amount={wallet.cost_basis[symbol]} currency={wallet.currency} />
                  </Table.Td>
                  <HoldingPriceAndValue symbol={symbol} valuation={valuation} />
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          </Table.ScrollContainer>
        )}
      </div>

      <div>
        <Title order={2} mb="sm">
          Operations
        </Title>
        {shownOperations.length === 0 ? (
          <Text c="dimmed">No operations yet. Use “Add operation” to record deposits and trades at their real dates.</Text>
        ) : (
          <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Date</Table.Th>
                <Table.Th>Type</Table.Th>
                <Table.Th>Symbol</Table.Th>
                <Table.Th ta="right">Quantity</Table.Th>
                <Table.Th ta="right">Price</Table.Th>
                <Table.Th ta="right">Amount</Table.Th>
                <Table.Th ta="right">Fees & tax</Table.Th>
                <Table.Th w={40} />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {/* Newest first, as in a statement. */}
              {[...shownOperations].reverse().map((op) => (
                <Table.Tr key={op.id}>
                  {/* Automatic operations (splits, dividends) happen on a date, not at a time. */}
                  <Table.Td>{op.automatic ? formatDate(op.timestamp.slice(0, 10)) : formatDateTime(op.timestamp)}</Table.Td>
                  <Table.Td>
                    <Group gap={6} wrap="nowrap">
                      <Text span inherit tt="capitalize">
                        {op.type}
                      </Text>
                      {op.automatic && <AutomaticBadge />}
                    </Group>
                  </Table.Td>
                  <Table.Td>{op.symbol ?? ""}</Table.Td>
                  <Table.Td ta="right">{op.type === OperationType.SPLIT ? `${op.split_old_rate} → ${op.split_new_rate}` : (op.quantity ?? "")}</Table.Td>
                  <Table.Td ta="right">
                    {op.price != null && op.price_currency && (
                      <Group gap={6} justify="flex-end" wrap="nowrap">
                        {op.price_source === PriceSource.MARKET && <MarketPriceBadge />}
                        <Money amount={op.price} currency={op.price_currency} />
                      </Group>
                    )}
                  </Table.Td>
                  <Table.Td ta="right">{op.type !== OperationType.SPLIT && <Money amount={op.amount} currency={wallet.currency} />}</Table.Td>
                  <Table.Td ta="right">
                    {/* Dividends: the tax withheld; Amount is what was credited after it. */}
                    {op.fees !== "0" && <Money amount={op.fees} currency={wallet.currency} />}
                    {op.withholding != null && Number(op.withholding) !== 0 && <Money amount={op.withholding} currency={wallet.currency} />}
                  </Table.Td>
                  <Table.Td>
                    {/* Automatic operations have no actions; they are marked in the Type column instead. */}
                    {/* Operations from market data or imports have no actions; the edit dialog only knows manual ones. */}
                    {isEditable(op) && <OperationActionsMenu operation={op} onEdit={onEditOperation} onDelete={onDeleteOperation} />}
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          </Table.ScrollContainer>
        )}
      </div>
    </Stack>
  );
}

/** The holding's latest price, its value in the wallet's currency, today's change and its gain, once the valuation has loaded. */
function HoldingPriceAndValue({ symbol, valuation }: { symbol: string; valuation: ValuationState }) {
  const loaded = valuation.status === "loaded" ? valuation.valuation : null;
  const holding = loaded?.holdings.find((h) => h.symbol === symbol);
  if (!loaded || !holding) {
    return (
      <>
        <Table.Td ta="right">{valuation.status === "loading" ? <Loader size="xs" /> : "—"}</Table.Td>
        <Table.Td ta="right">—</Table.Td>
        <Table.Td ta="right">—</Table.Td>
        <Table.Td ta="right">—</Table.Td>
      </>
    );
  }
  const fx = holding.fx_rate;
  const priceNote = [`As of ${formatDateTime(holding.as_of)}`, fx && `1 ${holding.currency} ≈ ${shortDecimal(fx.rate, RATE_DECIMALS)} ${loaded.currency} (${formatDate(fx.as_of)})`]
    .filter(Boolean)
    .join(" · ");
  return (
    <>
      <Table.Td ta="right">
        <Tooltip label={priceNote}>
          <Text span inherit>
            <Money amount={holding.price} currency={holding.currency} />
          </Text>
        </Tooltip>
      </Table.Td>
      <Table.Td ta="right">
        <Money amount={holding.value_in_wallet_currency} currency={loaded.currency} />
      </Table.Td>
      <Table.Td ta="right">
        {holding.day_change != null ? (
          <GainText amount={holding.day_change} currency={loaded.currency} percent={holding.day_change_percent} />
        ) : (
          "—"
        )}
      </Table.Td>
      <Table.Td ta="right">
        <GainText amount={holding.gain} currency={loaded.currency} percent={holding.gain_percent} />
      </Table.Td>
    </>
  );
}

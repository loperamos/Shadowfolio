import { Alert, Anchor, Box, Group, Loader, Skeleton, Stack, Table, Text, Title } from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";

import { apiErrorMessage } from "../api/errors";
import { listWallets, type WalletResponse } from "../api/generated";
import { walletPath } from "../routes";
import { GainText } from "../ui/GainText";
import { Money } from "../ui/Money";
import { formatDate, formatDateTime, todayAsInputValue } from "../ui/format";
import { InfoTip } from "../ui/InfoTip";
import { TimeSeriesChart } from "../ui/TimeSeriesChart";
import { CHART_HEIGHT, TABLE_MIN_WIDTH } from "../ui/theme";
import { symbolFilterSearch } from "../wallets/operationFilters";
import { PeriodControls } from "../wallets/PeriodControls";
import { describeRange, isEverything, usePeriod } from "../wallets/period";
import { type ValuationState, useWalletValuations } from "../wallets/useWalletValuation";
import { SecurityFundamentals } from "./SecurityFundamentals";
import { SecurityNews } from "./SecurityNews";
import { SecurityRanges } from "./SecurityRanges";
import { EXPLANATIONS } from "./explanations";
import { useCalendar, useCloses, useQuote } from "./useSecurity";

const CLOSE_LINE = "close";

/** One security: its latest price and today's move, its price over a period, its fundamentals, the wallets that hold it, and the latest news. */
export function SecurityPage() {
  const { symbol: raw = "" } = useParams();
  const symbol = raw.toUpperCase();
  // No breadcrumbs: a security does not sit inside a section (it is reached from the header's lookup, or a holding).
  return (
    <Stack gap="xl">
      <Header symbol={symbol} />
      <PriceChart symbol={symbol} />
      <SecurityFundamentals symbol={symbol} />
      <Positions symbol={symbol} />
      <SecurityNews symbol={symbol} />
    </Stack>
  );
}

function Header({ symbol }: { symbol: string }) {
  const state = useQuote(symbol);
  return (
    <div>
      <Title order={1}>{symbol}</Title>
      {state.status === "loading" && <Loader size="sm" mt="xs" />}
      {state.status === "error" && (
        <Alert color="yellow" mt="xs" title="Price unavailable">
          {state.message}
        </Alert>
      )}
      {state.status === "none" && (
        <Text c="dimmed" mt="xs">
          No market prices for {symbol}.
        </Text>
      )}
      {state.status === "loaded" && (
        <Group gap="md" align="baseline" mt="xs">
          <Money amount={state.quote.price} currency={state.quote.currency} size="xl" fw={600} />
          {state.quote.day_change != null && (
            <GainText amount={state.quote.day_change} currency={state.quote.currency} percent={state.quote.day_change_percent} size="lg" />
          )}
          <Text c="dimmed" size="sm">
            As of {formatDateTime(state.quote.as_of)}
          </Text>
        </Group>
      )}
      <NextDividend symbol={symbol} />
    </div>
  );
}

/** The next ex-dividend date announced, under the price; nothing while it loads. */
function NextDividend({ symbol }: { symbol: string }) {
  const state = useCalendar(symbol);
  if (state.status === "loading") {
    return null;
  }
  const dividend = state.status === "loaded" ? state.calendar.next_ex_dividend : null;
  return (
    <Group gap={4} mt={4} wrap="nowrap">
      <Text size="sm" c={dividend ? undefined : "dimmed"}>
        {state.status === "error" && `Dividends unavailable: ${state.message}`}
        {state.status === "loaded" && !dividend && "No dividend announced."}
        {dividend && (
          <>
            Next ex-dividend:{" "}
            <Text span inherit fw={600}>
              {formatDate(dividend.ex_date)}
            </Text>{" "}
            · <Money amount={dividend.per_share} currency={dividend.currency} /> a share
            {dividend.payable_date && `, paid ${formatDate(dividend.payable_date)}`}
          </>
        )}
      </Text>
      {state.status === "loaded" && <InfoTip topic="the ex-dividend date">{EXPLANATIONS.exDividend}</InfoTip>}
    </Group>
  );
}

function PriceChart({ symbol }: { symbol: string }) {
  const { period, range, choose } = usePeriod(todayAsInputValue());
  const state = useCloses(symbol, range.start, range.end);
  const [shown, setShown] = useState([CLOSE_LINE]);
  return (
    <div>
      <Group justify="space-between" align="flex-start" mb="sm">
        <Title order={2}>Price</Title>
        <PeriodControls period={period} range={range} onChoose={choose} />
      </Group>
      {state.status === "loading" && <Skeleton h={CHART_HEIGHT} />}
      {state.status === "error" && (
        <Alert color="yellow" title="Price history unavailable">
          {state.message}
        </Alert>
      )}
      {state.status === "loaded" &&
        (state.closes.length === 0 ? (
          <Text c="dimmed">No closing prices for {symbol}{isEverything(range) ? "" : ` ${describeRange(range)}`}.</Text>
        ) : (
          <TimeSeriesChart
            // For drawing only: the chart needs numbers. Prices stay exact strings everywhere else.
            points={state.closes.map((close) => ({ day: close.day, [CLOSE_LINE]: Number(close.close) }))}
            series={[{ name: CLOSE_LINE, label: "Close", color: "teal.6" }]}
            shown={shown}
            onShownChange={setShown}
            unit={state.closes[0].currency}
            onSelect={(start, end) => choose({ start, end })}
          />
        ))}
      <Box mt="lg">
        <SecurityRanges symbol={symbol} start={range.start} end={range.end} currency={state.status === "loaded" ? (state.closes[0]?.currency ?? null) : null} />
      </Box>
    </div>
  );
}

type WalletsState = { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; wallets: WalletResponse[] };

/** The wallets holding the symbol, with what the holding cost and is worth, and a link to its trades in each. */
function Positions({ symbol }: { symbol: string }) {
  const [state, setState] = useState<WalletsState>({ status: "loading" });
  useEffect(() => {
    let current = true;
    listWallets()
      .then(({ data, error }) => current && setState(data ? { status: "loaded", wallets: data } : { status: "error", message: apiErrorMessage(error) }))
      .catch(() => current && setState({ status: "error", message: "Could not reach the backend." }));
    return () => {
      current = false;
    };
  }, []);
  const holding = state.status === "loaded" ? state.wallets.filter((wallet) => wallet.holdings[symbol] !== undefined) : [];
  const valuations = useWalletValuations(holding.map((wallet) => wallet.id));

  return (
    <div>
      <Title order={2} mb="sm">
        Your positions
      </Title>
      {state.status === "loading" && <Loader size="sm" />}
      {state.status === "error" && <Alert color="yellow">{state.message}</Alert>}
      {state.status === "loaded" &&
        (holding.length === 0 ? (
          <Text c="dimmed">None of your wallets holds {symbol}.</Text>
        ) : (
          <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Wallet</Table.Th>
                  <Table.Th ta="right">Shares</Table.Th>
                  <Table.Th ta="right">Cost</Table.Th>
                  <Table.Th ta="right">Value</Table.Th>
                  <Table.Th ta="right">Gain</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {holding.map((wallet) => (
                  <Table.Tr key={wallet.id}>
                    <Table.Td>
                      <Anchor component={Link} to={walletPath(wallet.id)}>
                        {wallet.name}
                      </Anchor>
                    </Table.Td>
                    <Table.Td ta="right">{wallet.holdings[symbol]}</Table.Td>
                    <Table.Td ta="right">
                      <Money amount={wallet.cost_basis[symbol]} currency={wallet.currency} />
                    </Table.Td>
                    <HoldingCells symbol={symbol} valuation={valuations[wallet.id]} />
                    <Table.Td ta="right">
                      <Anchor component={Link} to={{ pathname: walletPath(wallet.id), search: symbolFilterSearch(symbol) }} size="sm">
                        Trades
                      </Anchor>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        ))}
    </div>
  );
}

/** The holding's value and gain from the wallet's valuation, once loaded. */
function HoldingCells({ symbol, valuation }: { symbol: string; valuation: ValuationState | undefined }) {
  const loaded = valuation?.status === "loaded" ? valuation.valuation : null;
  const holding = loaded?.holdings.find((h) => h.symbol === symbol);
  if (!loaded || !holding) {
    const placeholder = valuation === undefined || valuation.status === "loading" ? <Loader size="xs" /> : "—";
    return (
      <>
        <Table.Td ta="right">{placeholder}</Table.Td>
        <Table.Td ta="right">{placeholder}</Table.Td>
      </>
    );
  }
  return (
    <>
      <Table.Td ta="right">
        <Money amount={holding.value_in_wallet_currency} currency={loaded.currency} />
      </Table.Td>
      <Table.Td ta="right">
        <GainText amount={holding.gain} currency={loaded.currency} percent={holding.gain_percent} />
      </Table.Td>
    </>
  );
}

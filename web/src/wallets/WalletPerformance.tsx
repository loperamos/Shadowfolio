import { Alert, Group, Skeleton, Table, Text, TextInput, Title } from "@mantine/core";
import { type ReactNode, useState } from "react";

import type { PerformanceResponse } from "../api/generated";
import { GainText, ReturnText } from "../ui/GainText";
import { formatDate } from "../ui/format";
import { CHART_HEIGHT, SYMBOL_INPUT_WIDTH } from "../ui/theme";
import type { DayRange } from "./period";
import { usePerformance } from "./usePerformance";

type Props = {
  walletId: string;
  currency: string;
  range: DayRange;
  refreshKey: number;
  // The benchmark's symbol (null for the default), and a way to choose another.
  benchmarkSymbol: string | null;
  onBenchmarkChange: (symbol: string | null) => void;
};

/** How the wallet did over the chart's period, next to a benchmark with the same deposits, chosen here. */
export function WalletPerformance({ walletId, currency, range, refreshKey, benchmarkSymbol, onBenchmarkChange }: Props) {
  const state = usePerformance(walletId, range.start, range.end, benchmarkSymbol, refreshKey);
  const shownSymbol = state.status === "loaded" ? state.comparison.benchmark_symbol : null;
  return (
    <div>
      <Group justify="space-between" align="flex-start" mb="sm">
        <Title order={2}>Performance</Title>
        <BenchmarkField symbol={benchmarkSymbol} placeholder={shownSymbol} onChange={onBenchmarkChange} />
      </Group>
      <PerformanceBody state={state} currency={currency} />
    </div>
  );
}

/**
 * The benchmark to compare with: any symbol market data prices (e.g. QQQ, URTH). Applied on Enter or on leaving the
 * field, not on every letter; empty goes back to the default, shown as the placeholder.
 */
function BenchmarkField({ symbol, placeholder, onChange }: { symbol: string | null; placeholder: string | null; onChange: (symbol: string | null) => void }) {
  const [text, setText] = useState(symbol ?? "");
  // Follow changes made elsewhere (e.g. a link), as the field keeps its own text while typing.
  const [shown, setShown] = useState(symbol);
  if (symbol !== shown) {
    setShown(symbol);
    setText(symbol ?? "");
  }
  const apply = () => text.trim().toUpperCase() !== (symbol ?? "") && onChange(text);
  return (
    <TextInput
      size="xs"
      aria-label="Compare with (symbol)"
      leftSection={<Text size="xs">vs</Text>}
      placeholder={placeholder ?? undefined}
      w={SYMBOL_INPUT_WIDTH}
      value={text}
      onChange={(event) => setText(event.currentTarget.value.toUpperCase())}
      onBlur={apply}
      onKeyDown={(event) => event.key === "Enter" && apply()}
    />
  );
}

function PerformanceBody({ state, currency }: { state: ReturnType<typeof usePerformance>; currency: string }) {
  switch (state.status) {
    case "loading":
      return <Skeleton h={CHART_HEIGHT / 2} />;
    case "error":
      return (
        <Alert color="yellow" title="Performance unavailable">
          {state.message}
        </Alert>
      );
    case "loaded": {
      const { wallet, benchmark, benchmark_symbol } = state.comparison;
      if (wallet === null) {
        return <Text c="dimmed">Nothing could be valued in this period.</Text>;
      }
      const columns = [wallet, benchmark];
      const row = (label: string, description: string, cell: (result: PerformanceResponse) => ReactNode) => (
        <Table.Tr>
          <Table.Td>
            <Text inherit>{label}</Text>
            <Text c="dimmed" size="xs">
              {description}
            </Text>
          </Table.Td>
          {columns.map((result, index) => (
            <Table.Td key={index} ta="right">
              {result === null ? <Text c="dimmed">—</Text> : cell(result)}
            </Table.Td>
          ))}
        </Table.Tr>
      );
      return (
        <>
          <Text c="dimmed" size="sm" mb="xs">
            From the end of {formatDate(wallet.start_day)} to the end of {formatDate(wallet.end_day)}.
            {/* The benchmark can start later, e.g. when its prices start: say so, as the periods then differ. */}
            {benchmark !== null && benchmark.start_day !== wallet.start_day && ` ${benchmark_symbol} from the end of ${formatDate(benchmark.start_day)}, its first day with a price.`}
            {benchmark === null && ` No market prices for ${benchmark_symbol} in this period: there is nothing to compare with.`}
          </Text>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th />
                <Table.Th ta="right">Your wallet</Table.Th>
                <Table.Th ta="right">{benchmark_symbol} with the same deposits</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {row("Gain", "End value less start value and money put in", (result) => (
                <GainText amount={result.gain} currency={currency} />
              ))}
              {row("Return", "Time-weighted: what was held, whatever money moved", (result) => (
                <PerReturn total={result.time_weighted_return} perYear={result.time_weighted_return_per_year} />
              ))}
              {row("Return on your money", "Money-weighted: with when money went in and out", (result) =>
                result.money_weighted_return === null ? (
                  <Text c="dimmed">—</Text>
                ) : (
                  <PerReturn total={result.money_weighted_return} perYear={result.money_weighted_return_per_year} />
                ),
              )}
            </Table.Tbody>
          </Table>
        </>
      );
    }
  }
}

/** A return over the period, and per year when the period is a year or more. */
function PerReturn({ total, perYear }: { total: string; perYear: string | null }) {
  return (
    <>
      <ReturnText percent={total} />
      {perYear !== null && (
        <Text c="dimmed" size="xs">
          <ReturnText percent={perYear} suffix="a year" />
        </Text>
      )}
    </>
  );
}

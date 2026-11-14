import { Alert, Skeleton, Table, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";

import type { PerformanceResponse } from "../api/generated";
import { GainText, ReturnText } from "../ui/GainText";
import { formatDate } from "../ui/format";
import { CHART_HEIGHT } from "../ui/theme";
import type { DayRange } from "./period";
import { usePerformance } from "./usePerformance";

type Props = { walletId: string; currency: string; range: DayRange; refreshKey: number };

/** How the wallet did over the chart's period, next to the benchmark with the same deposits. */
export function WalletPerformance({ walletId, currency, range, refreshKey }: Props) {
  const state = usePerformance(walletId, range.start, range.end, refreshKey);
  return (
    <div>
      <Title order={2} mb="sm">
        Performance
      </Title>
      <PerformanceBody state={state} currency={currency} />
    </div>
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

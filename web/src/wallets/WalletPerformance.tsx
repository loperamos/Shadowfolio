import { Alert, Group, Skeleton, Text, Title } from "@mantine/core";

import type { TradingActivityResponse } from "../api/generated";
import { Figure } from "../ui/Figure";
import { formatDate, formatPercent } from "../ui/format";
import { Money } from "../ui/Money";
import { CHART_HEIGHT } from "../ui/theme";
import { BenchmarkField } from "./BenchmarkField";
import { PerformanceTable } from "./PerformanceTable";
import type { DayRange } from "./period";
import { usePerformance } from "./usePerformance";
import { WalletContributions } from "./WalletContributions";

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
      const { wallet, benchmark, benchmark_symbol, trading, contributions, other_gain } = state.comparison;
      if (wallet === null) {
        return <Text c="dimmed">Nothing could be valued in this period.</Text>;
      }
      return (
        <>
          <Text c="dimmed" size="sm" mb="xs">
            From the end of {formatDate(wallet.start_day)} to the end of {formatDate(wallet.end_day)}.
            {/* The benchmark can start later, e.g. when its prices start: say so, as the periods then differ. */}
            {benchmark !== null && benchmark.start_day !== wallet.start_day && ` ${benchmark_symbol} from the end of ${formatDate(benchmark.start_day)}, its first day with a price.`}
            {benchmark === null && ` No market prices for ${benchmark_symbol} in this period: there is nothing to compare with.`}
          </Text>
          <PerformanceTable
            columns={[
              { key: "wallet", label: "Your wallet", result: wallet, currency },
              { key: "benchmark", label: `${benchmark_symbol} with the same deposits`, result: benchmark, currency },
            ]}
          />
          <Trading trading={trading} currency={currency} />
          <WalletContributions contributions={contributions} otherGain={other_gain} currency={currency} />
        </>
      );
    }
  }
}

/**
 * What the wallet traded in the period and what it cost, against its average value: frequent trading and its costs are
 * what most hurt individual investors' returns (Barber & Odean, 2000).
 */
function Trading({ trading, currency }: { trading: TradingActivityResponse; currency: string }) {
  const percent = (value: string | null) => (value === null ? "—" : `${formatPercent(value)}%`);
  return (
    <Group gap="xl" mt="md" align="flex-start">
      <Figure label="Bought" explanation="Spent on buys in this period, before fees.">
        <Money amount={trading.bought} currency={currency} />
      </Figure>
      <Figure label="Sold" explanation="Received from sells in this period, before fees.">
        <Money amount={trading.sold} currency={currency} />
      </Figure>
      <Figure
        label="Turnover"
        explanation="The share of the wallet replaced in this period: the smaller of what was bought and sold, against the wallet's average value, as funds report it. Buying with new money, or selling to take money out, does not count."
      >
        {percent(trading.turnover_percent)}
      </Figure>
      <Figure
        label="Fees"
        explanation="Paid on trades and charged on their own in this period, and their share of the wallet's average value. Every fee comes straight off the return."
        note={trading.fees_percent === null ? undefined : `${percent(trading.fees_percent)} of the average value`}
      >
        <Money amount={trading.fees} currency={currency} />
      </Figure>
    </Group>
  );
}

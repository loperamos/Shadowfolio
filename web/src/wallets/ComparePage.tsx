import { Alert, Anchor, Breadcrumbs, Group, Skeleton, Stack, Text, Title } from "@mantine/core";
import { useState } from "react";
import { Link, useSearchParams } from "react-router";

import { COMPARED_WALLETS_PARAM, COMPARED_WALLETS_SEPARATOR, walletPath, WALLETS_PATH } from "../routes";
import { formatDate, todayAsInputValue } from "../ui/format";
import { PERCENT, TimeSeriesChart } from "../ui/TimeSeriesChart";
import { CHART_HEIGHT, COMPARISON_COLORS } from "../ui/theme";
import { BenchmarkField } from "./BenchmarkField";
import { useBenchmarkChoice } from "./benchmarkChoice";
import { HindsightBadge } from "./HindsightBadges";
import { type PerformanceColumn, PerformanceTable } from "./PerformanceTable";
import { PeriodControls } from "./PeriodControls";
import { usePeriod } from "./period";
import { type ComparedWallet, type LoadedWallet, useComparison } from "./useComparison";

const MIN_WALLETS = 2;
// The benchmark's line, among the wallets' (keyed by wallet id).
const BENCHMARK_LINE = "benchmark";
const BENCHMARK_COLOR = "indigo.6";

/**
 * Wallets side by side over a period: their returns over time (in percent, so wallets of any size compare) and their
 * performance, next to a benchmark. Wallets with trades priced with hindsight say so.
 */
export function ComparePage() {
  const [params] = useSearchParams();
  const ids = (params.get(COMPARED_WALLETS_PARAM) ?? "").split(COMPARED_WALLETS_SEPARATOR).filter(Boolean);
  const { period, range, choose } = usePeriod(todayAsInputValue());
  const [benchmarkSymbol, chooseBenchmark] = useBenchmarkChoice();
  const compared = useComparison(ids, range.start, range.end, benchmarkSymbol);
  // Every wallet's line at first; the benchmark's on demand, as in the wallet page.
  const [shown, setShown] = useState<string[]>(ids);

  const breadcrumbs = (
    <Breadcrumbs mb="md">
      <Anchor component={Link} to={WALLETS_PATH}>
        Wallets
      </Anchor>
      <Text>Compare</Text>
    </Breadcrumbs>
  );
  if (ids.length < MIN_WALLETS) {
    return (
      <>
        {breadcrumbs}
        <Alert color="yellow" title="Nothing to compare">
          Select two or more wallets in{" "}
          <Anchor component={Link} to={WALLETS_PATH}>
            your wallets
          </Anchor>{" "}
          and choose Compare.
        </Alert>
      </>
    );
  }

  const loaded = ids.flatMap((id) => {
    const state = compared[id];
    return state?.status === "loaded" ? [{ id, ...state }] : [];
  });
  // The benchmark as the first loaded wallet sees it (its returns barely depend on the wallet: only its withholding tax).
  const benchmark = loaded[0];
  const symbol = benchmark?.performance.benchmark_symbol ?? null;
  const name = (id: string) => loaded.find((wallet) => wallet.id === id)?.wallet.name ?? "…";

  return (
    <>
      {breadcrumbs}
      <Title order={1} mb="lg">
        Compare wallets
      </Title>
      <Stack gap="xl">
        <div>
          <Group justify="space-between" align="flex-start" mb="sm">
            <Title order={2}>Returns over time</Title>
            <PeriodControls period={period} range={range} onChoose={choose} />
          </Group>
          {loaded.length === 0 ? (
            <Skeleton h={CHART_HEIGHT} />
          ) : (
            <TimeSeriesChart
              unit={PERCENT}
              shaded={false}
              points={returnPoints(loaded, benchmark)}
              series={[
                ...ids.map((id, index) => ({ name: id, label: name(id), color: COMPARISON_COLORS[index % COMPARISON_COLORS.length] })),
                { name: BENCHMARK_LINE, label: symbol ?? "Benchmark", color: BENCHMARK_COLOR, dashed: true },
              ]}
              shown={shown}
              onShownChange={setShown}
              onSelect={(start, end) => choose({ start, end })}
            />
          )}
          <Text c="dimmed" size="sm" mt="xs">
            Time-weighted returns since the start of the period: what each wallet held, whatever money went in or out,
            so wallets of any size compare.
          </Text>
          {ids.map((id) => {
            const state = compared[id];
            return state?.status === "error" ? (
              <Alert key={id} color="yellow" mt="xs" title={`Wallet ${id.slice(0, 8)}… unavailable`}>
                {state.message}
              </Alert>
            ) : null;
          })}
        </div>

        <div>
          <Group justify="space-between" align="flex-start" mb="sm">
            <Title order={2}>Performance</Title>
            <BenchmarkField symbol={benchmarkSymbol} placeholder={symbol} onChange={chooseBenchmark} />
          </Group>
          {loaded.length === 0 ? (
            <Skeleton h={CHART_HEIGHT / 2} />
          ) : (
            <>
              <Text c="dimmed" size="sm" mb="xs">
                {periodLine(loaded)}
              </Text>
              <PerformanceTable columns={performanceColumns(ids, compared, benchmark)} />
            </>
          )}
        </div>
      </Stack>
    </>
  );
}

// For drawing only: the chart needs numbers. Returns stay exact strings everywhere else.
function returnPoints(loaded: LoadedWallet[], benchmark: LoadedWallet | undefined) {
  const byDay = new Map<string, Record<string, number | null>>();
  const add = (day: string, line: string, value: string | null) => {
    byDay.set(day, { ...byDay.get(day), [line]: value == null ? null : Number(value) });
  };
  for (const { id, performance } of loaded) {
    performance.wallet_returns.forEach(({ day, value }) => add(day, id, value));
  }
  benchmark?.performance.benchmark_returns.forEach(({ day, value }) => add(day, BENCHMARK_LINE, value));
  return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([day, values]) => ({ day, ...values }));
}

function performanceColumns(ids: string[], compared: Record<string, ComparedWallet>, benchmark: LoadedWallet | undefined): PerformanceColumn[] {
  const columns = ids.map((id): PerformanceColumn => {
    const state = compared[id];
    if (state?.status !== "loaded") {
      return { key: id, label: state?.status === "error" ? "Unavailable" : "Loading…", result: null, currency: "" };
    }
    return {
      key: id,
      label: (
        <Group gap={6} justify="flex-end" wrap="nowrap">
          <Anchor component={Link} to={walletPath(id)}>
            {state.wallet.name}
          </Anchor>
          {state.wallet.hindsight && <HindsightBadge />}
        </Group>
      ),
      result: state.performance.wallet,
      currency: state.wallet.currency,
    };
  });
  if (benchmark) {
    const { benchmark_symbol, benchmark: result } = benchmark.performance;
    columns.push({ key: BENCHMARK_LINE, label: `${benchmark_symbol} with the same deposits as ${benchmark.wallet.name}`, result, currency: benchmark.wallet.currency });
  }
  return columns;
}

/** The period the figures cover, with each wallet's first day when they differ (e.g. one opened later). */
function periodLine(loaded: LoadedWallet[]): string {
  const starts = loaded.flatMap(({ wallet, performance }) => (performance.wallet ? [{ name: wallet.name, day: performance.wallet.start_day }] : []));
  const ends = loaded.flatMap(({ performance }) => (performance.wallet ? [performance.wallet.end_day] : []));
  if (starts.length === 0) {
    return "Nothing could be valued in this period.";
  }
  const end = formatDate(ends.sort().at(-1) ?? starts[0].day);
  if (new Set(starts.map((start) => start.day)).size === 1) {
    return `From the end of ${formatDate(starts[0].day)} to the end of ${end}.`;
  }
  return `To the end of ${end}, each from its first day in the period: ${starts.map((start) => `${start.name} ${formatDate(start.day)}`).join(", ")}.`;
}

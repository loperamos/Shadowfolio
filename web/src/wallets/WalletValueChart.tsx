import { Alert, Group, SegmentedControl, Skeleton, Text, Title } from "@mantine/core";

import type { DailyValueResponse } from "../api/generated";
import { TimeSeriesChart } from "../ui/TimeSeriesChart";
import { CHART_HEIGHT } from "../ui/theme";
import { formatDate } from "../ui/format";
import { Period, periodStart } from "./period";
import { useDailyValues } from "./useDailyValues";

type ChartProps = {
  walletId: string;
  currency: string;
  refreshKey: number;
  period: Period;
  // The first day of the period (YYYY-MM-DD); null for everything.
  start: string | null;
  onPeriodChange: (period: Period) => void;
};

/** The wallet's value over time against the money put in, over a period chosen here (which the page also follows). */
export function WalletValueChart({ walletId, currency, refreshKey, period, start, onPeriodChange }: ChartProps) {
  const state = useDailyValues(walletId, refreshKey);
  return (
    <div>
      <Group justify="space-between" mb="sm">
        <Title order={2}>Value over time</Title>
        <SegmentedControl
          size="xs"
          aria-label="Period"
          data={Object.values(Period)}
          value={period}
          onChange={(value) => onPeriodChange(value as Period)}
        />
      </Group>
      <ChartBody state={state} start={start} currency={currency} />
    </div>
  );
}

function ChartBody({ state, start, currency }: { state: ReturnType<typeof useDailyValues>; start: string | null; currency: string }) {
  switch (state.status) {
    case "loading":
      return <Skeleton h={CHART_HEIGHT} />;
    case "error":
      return (
        <Alert color="yellow" title="Value over time unavailable">
          {state.message}
        </Alert>
      );
    case "loaded": {
      if (state.values.length === 0) {
        return <Text c="dimmed">No history yet. Add an operation to see the wallet’s value over time.</Text>;
      }
      const shown = start === null ? state.values : state.values.filter((value) => value.day >= start);
      if (start !== null && shown.length === 0) {
        return <Text c="dimmed">No history since {formatDate(start)}.</Text>;
      }
      const unvalued = shown.filter((value) => value.missing.length > 0);
      const missing = [...new Set(unvalued.flatMap((value) => value.missing))];
      return (
        <>
          <TimeSeriesChart
            points={shown.map(toPoint)}
            currency={currency}
            series={[
              { name: "total", label: "Value", color: "teal.6" },
              { name: "net_deposits", label: "Net deposits", color: "gray.6", dashed: true },
            ]}
          />
          {/* Unvalued days are gaps in the line, never guesses; say why. */}
          {unvalued.length > 0 && (
            <Text c="dimmed" size="sm" mt="xs">
              Not valued on {unvalued.length} of these {shown.length} days: no price or exchange rate for {missing.join(", ")}.
            </Text>
          )}
        </>
      );
    }
  }
}

// For drawing only: the chart needs numbers. Amounts stay exact strings everywhere else.
function toPoint(value: DailyValueResponse) {
  return { day: value.day, total: value.total == null ? null : Number(value.total), net_deposits: Number(value.net_deposits) };
}

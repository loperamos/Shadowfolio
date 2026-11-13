import { Alert, Group, SegmentedControl, Skeleton, Text, Title } from "@mantine/core";
import dayjs from "dayjs";
import { useState } from "react";

import type { DailyValueResponse } from "../api/generated";
import { TimeSeriesChart } from "../ui/TimeSeriesChart";
import { CHART_HEIGHT } from "../ui/theme";
import { useDailyValues } from "./useDailyValues";

// Periods to show, ending on the last day with a value, as on most brokers' and finance sites' charts.
enum Range {
  MONTH = "1M",
  HALF_YEAR = "6M",
  YEAR_TO_DATE = "YTD",
  YEAR = "1Y",
  ALL = "All",
}

/** The first day shown for `range`, given the last day with a value (YYYY-MM-DD); null shows everything. */
function rangeStart(range: Range, lastDay: string): string | null {
  const last = dayjs(lastDay);
  switch (range) {
    case Range.MONTH:
      return last.subtract(1, "month").format("YYYY-MM-DD");
    case Range.HALF_YEAR:
      return last.subtract(6, "month").format("YYYY-MM-DD");
    case Range.YEAR_TO_DATE:
      return last.startOf("year").format("YYYY-MM-DD");
    case Range.YEAR:
      return last.subtract(1, "year").format("YYYY-MM-DD");
    case Range.ALL:
      return null;
  }
}

/** The wallet's value over time against the money put in, with a choice of period. */
export function WalletValueChart({ walletId, currency, refreshKey }: { walletId: string; currency: string; refreshKey: number }) {
  const state = useDailyValues(walletId, refreshKey);
  const [range, setRange] = useState(Range.ALL);
  return (
    <div>
      <Group justify="space-between" mb="sm">
        <Title order={2}>Value over time</Title>
        <SegmentedControl
          size="xs"
          aria-label="Period"
          data={Object.values(Range)}
          value={range}
          onChange={(value) => setRange(value as Range)}
          disabled={state.status !== "loaded" || state.values.length === 0}
        />
      </Group>
      <ChartBody state={state} range={range} currency={currency} />
    </div>
  );
}

function ChartBody({ state, range, currency }: { state: ReturnType<typeof useDailyValues>; range: Range; currency: string }) {
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
      const start = rangeStart(range, state.values[state.values.length - 1].day);
      const shown = start === null ? state.values : state.values.filter((value) => value.day >= start);
      return (
        <TimeSeriesChart
          points={shown.map(toPoint)}
          currency={currency}
          series={[
            { name: "total", label: "Value", color: "teal.6" },
            { name: "net_deposits", label: "Net deposits", color: "gray.6", dashed: true },
          ]}
        />
      );
    }
  }
}

// For drawing only: the chart needs numbers. Amounts stay exact strings everywhere else.
function toPoint(value: DailyValueResponse) {
  return { day: value.day, total: Number(value.total), net_deposits: Number(value.net_deposits) };
}

import { Alert, Group, SegmentedControl, Skeleton, Text, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconCalendar } from "@tabler/icons-react";

import type { DailyValueResponse } from "../api/generated";
import { TimeSeriesChart } from "../ui/TimeSeriesChart";
import { DATE_INPUT_FORMAT, parseDateInput } from "../ui/format";
import { CHART_HEIGHT, DATE_INPUT_WIDTH, ICON_SIZE } from "../ui/theme";
import { type DayRange, describeRange, inRange, isEverything, Period } from "./period";
import { useDailyValues } from "./useDailyValues";

type ChartProps = {
  walletId: string;
  currency: string;
  refreshKey: number;
  // The preset shown, or null for chosen dates; `range` is the days either covers.
  period: Period | null;
  range: DayRange;
  onChoose: (choice: Period | DayRange) => void;
};

/** The wallet's value over time against the money put in, over a period chosen here (which the page also follows). */
export function WalletValueChart({ walletId, currency, refreshKey, period, range, onChoose }: ChartProps) {
  const state = useDailyValues(walletId, refreshKey);
  const backwards = range.start !== null && range.end !== null && range.start > range.end;
  return (
    <div>
      <Group justify="space-between" align="flex-start" mb="sm">
        <Title order={2}>Value over time</Title>
        <Group gap="xs" align="flex-start">
          {/* A preset, or dates typed or picked: as in Grafana's and Google Analytics' period pickers. */}
          <SegmentedControl size="xs" aria-label="Period" data={Object.values(Period)} value={period ?? ""} onChange={(value) => onChoose(value as Period)} />
          <DayInput label="From" placeholder="First day" value={range.start} onChange={(start) => onChoose({ ...range, start })} />
          <DayInput
            label="To"
            placeholder="Today"
            value={range.end}
            onChange={(end) => onChoose({ ...range, end })}
            error={backwards ? "Before “From”" : undefined}
          />
        </Group>
      </Group>
      <ChartBody state={state} range={range} currency={currency} onSelect={(start, end) => onChoose({ start, end })} />
    </div>
  );
}

type DayInputProps = { label: string; placeholder: string; value: string | null; onChange: (value: string | null) => void; error?: string };

function DayInput({ label, placeholder, value, onChange, error }: DayInputProps) {
  return (
    <DateInput
      size="xs"
      aria-label={label}
      w={DATE_INPUT_WIDTH}
      placeholder={placeholder}
      valueFormat={DATE_INPUT_FORMAT}
      dateParser={parseDateInput}
      leftSection={<IconCalendar size={ICON_SIZE} />}
      clearable
      value={value}
      onChange={onChange}
      error={error}
    />
  );
}

type BodyProps = { state: ReturnType<typeof useDailyValues>; range: DayRange; currency: string; onSelect: (start: string, end: string) => void };

function ChartBody({ state, range, currency, onSelect }: BodyProps) {
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
      const shown = state.values.filter((value) => inRange(value.day, range));
      if (!isEverything(range) && shown.length === 0) {
        return <Text c="dimmed">No history {describeRange(range)}.</Text>;
      }
      const unvalued = shown.filter((value) => value.missing.length > 0);
      const missing = [...new Set(unvalued.flatMap((value) => value.missing))];
      return (
        <>
          <TimeSeriesChart
            points={shown.map(toPoint)}
            currency={currency}
            onSelect={onSelect}
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

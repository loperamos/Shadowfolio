import { Alert, Group, SegmentedControl, Skeleton, Text, Title } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { IconCalendar } from "@tabler/icons-react";
import { memo } from "react";
import { useSearchParams } from "react-router";

import { useUpdateQuery } from "../ui/url";

import type { DailyValueResponse } from "../api/generated";
import { TimeSeriesChart } from "../ui/TimeSeriesChart";
import { DATE_INPUT_FORMAT, parseDateInput } from "../ui/format";
import { CHART_HEIGHT, DATE_INPUT_WIDTH, ICON_SIZE } from "../ui/theme";
import { type DayRange, describeRange, inRange, isEverything, Period } from "./period";
import { type BenchmarkState, useBenchmark } from "./useBenchmark";
import { useDailyValues } from "./useDailyValues";

// The chart's lines, by the key of their values in each point.
enum Line {
  VALUE = "total",
  NET_DEPOSITS = "net_deposits",
  BENCHMARK = "benchmark",
}

// Net deposits is hidden at first: after taking out more than was put in, it is far below the value and squashes it.
const DEFAULT_LINES: string[] = [Line.VALUE];
// The lines shown, in the URL (?lines=total,net_deposits) when not the default ones, so a view can be shared.
const LINES_PARAM = "lines";
const LINES_SEPARATOR = ",";

/** The chart's lines shown, from the URL, and a way to change them. */
export function useChartLines(): [string[], (lines: string[]) => void] {
  const [params] = useSearchParams();
  const updateQuery = useUpdateQuery();
  const value = params.get(LINES_PARAM);
  const known: string[] = Object.values(Line);
  const lines = value === null ? DEFAULT_LINES : value.split(LINES_SEPARATOR).filter((line) => known.includes(line));
  function setLines(next: string[]) {
    updateQuery((current) => {
      const updated = new URLSearchParams(current);
      const isDefault = next.length === DEFAULT_LINES.length && next.every((line) => DEFAULT_LINES.includes(line));
      if (isDefault) {
        updated.delete(LINES_PARAM);
      } else {
        updated.set(LINES_PARAM, next.join(LINES_SEPARATOR));
      }
      return updated;
    });
  }
  return [lines, setLines];
}

type ChartProps = {
  walletId: string;
  currency: string;
  refreshKey: number;
  // The preset shown, or null for chosen dates; `range` is the days either covers.
  period: Period | null;
  range: DayRange;
  onChoose: (choice: Period | DayRange) => void;
  // The lines shown (see useChartLines).
  lines: string[];
  onLinesChange: (lines: string[]) => void;
};

/** The wallet's value over time against the money put in, over a period chosen here (which the page also follows). */
function WalletValueChartView({ walletId, currency, refreshKey, period, range, onChoose, lines, onLinesChange }: ChartProps) {
  const state = useDailyValues(walletId, refreshKey);
  const benchmark = useBenchmark(walletId, refreshKey);
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
      <ChartBody
        state={state}
        benchmark={benchmark}
        range={range}
        currency={currency}
        onSelect={(start, end) => onChoose({ start, end })}
        lines={lines}
        onLinesChange={onLinesChange}
      />
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

/**
 * The chart, drawn again only when what it shows changes: drawing thousands of days is slow, and the rest of the page
 * (sorting, filters, pages) changes the URL often. Its callbacks change the URL as it is when
 * called (see useUpdateQuery), so an earlier one does the same as a new one.
 */
export const WalletValueChart = memo(
  WalletValueChartView,
  (before, after) =>
    before.walletId === after.walletId &&
    before.currency === after.currency &&
    before.refreshKey === after.refreshKey &&
    before.period === after.period &&
    before.range.start === after.range.start &&
    before.range.end === after.range.end &&
    before.lines.join() === after.lines.join(),
);

type BodyProps = {
  state: ReturnType<typeof useDailyValues>;
  benchmark: BenchmarkState;
  range: DayRange;
  currency: string;
  onSelect: (start: string, end: string) => void;
  lines: string[];
  onLinesChange: (lines: string[]) => void;
};

function ChartBody({ state, benchmark, range, currency, onSelect, lines, onLinesChange }: BodyProps) {
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
      const withEstimates = shown.filter((value) => value.estimated.length > 0);
      const estimated = [...new Set(withEstimates.flatMap((value) => value.estimated))];
      // The benchmark comes on its own; until then (or if it fails) its line has no points.
      const benchmarkValues = new Map(benchmark.status === "loaded" ? benchmark.benchmark.values.map((v) => [v.day, v.value]) : []);
      const benchmarkLabel = `${benchmark.status === "loaded" ? benchmark.benchmark.symbol : "Benchmark"} with the same deposits`;
      return (
        <>
          <TimeSeriesChart
            points={shown.map((value) => toPoint(value, benchmarkValues.get(value.day)))}
            currency={currency}
            onSelect={onSelect}
            series={[
              { name: Line.VALUE, label: "Value", color: "teal.6" },
              { name: Line.NET_DEPOSITS, label: "Net deposits", color: "gray.6", dashed: true },
              { name: Line.BENCHMARK, label: benchmarkLabel, color: "indigo.6" },
            ]}
            shown={lines}
            onShownChange={onLinesChange}
          />
          {lines.includes(Line.BENCHMARK) && benchmark.status === "error" && (
            <Text c="dimmed" size="sm" mt="xs">
              {benchmarkLabel} unavailable: {benchmark.message}
            </Text>
          )}
          {/* Estimated prices are only for listings market data does not cover; say which, and on how many days. */}
          {withEstimates.length > 0 && (
            <Text c="dimmed" size="sm" mt="xs">
              Estimated on {withEstimates.length} of these {shown.length} days: no market prices for {estimated.join(", ")}, so they are valued
              at the price you last traded them at (or next, if you had not yet).
            </Text>
          )}
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
function toPoint(value: DailyValueResponse, benchmark: string | null | undefined) {
  return {
    day: value.day,
    [Line.VALUE]: value.total == null ? null : Number(value.total),
    [Line.NET_DEPOSITS]: Number(value.net_deposits),
    [Line.BENCHMARK]: benchmark == null ? null : Number(benchmark),
  };
}

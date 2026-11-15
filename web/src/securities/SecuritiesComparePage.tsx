import { Alert, Skeleton, Stack, TagsInput, Text, Title, Group } from "@mantine/core";
import { useState } from "react";
import { useSearchParams } from "react-router";

import type { DailyCloseResponse } from "../api/generated";
import { COMPARED_SYMBOLS_PARAM, COMPARED_SYMBOLS_SEPARATOR } from "../routes";
import { todayAsInputValue } from "../ui/format";
import { PERCENT, TimeSeriesChart } from "../ui/TimeSeriesChart";
import { CHART_HEIGHT, COMPARISON_COLORS } from "../ui/theme";
import { useUpdateQuery } from "../ui/url";
import { PeriodControls } from "../wallets/PeriodControls";
import { describeRange, isEverything, usePeriod } from "../wallets/period";
import { SecuritiesSideBySide } from "./SecuritiesSideBySide";
import { type ClosesState, useClosesOf, useSummariesOf } from "./useSecurity";

// As many securities as the chart has distinct colours for.
const MAX_SYMBOLS = COMPARISON_COLORS.length;
const PERCENT_FACTOR = 100;

/** Securities side by side: how each price changed over a period, from the same start, whatever its level. */
export function SecuritiesComparePage() {
  const [symbols, setSymbols] = useComparedSymbols();
  const { period, range, choose } = usePeriod(todayAsInputValue());
  const closes = useClosesOf(symbols, range.start, range.end);
  const summaries = useSummariesOf(symbols, range.start, range.end);
  // Lines switched off in the legend; every symbol's is drawn otherwise.
  const [hidden, setHidden] = useState<string[]>([]);
  const loaded = symbols.flatMap((symbol) => {
    const state = closes[symbol];
    return state?.status === "loaded" && state.closes.length > 0 ? [{ symbol, closes: state.closes }] : [];
  });

  return (
    <Stack gap="xl">
      <Title order={1}>Compare securities</Title>
      <TagsInput
        label="Securities"
        description={`Type a symbol and press Enter; up to ${MAX_SYMBOLS}.`}
        placeholder={symbols.length < MAX_SYMBOLS ? "e.g. NVDA" : undefined}
        maxTags={MAX_SYMBOLS}
        value={symbols}
        onChange={(values) => setSymbols([...new Set(values.map((value) => value.trim().toUpperCase()).filter(Boolean))])}
      />
      {symbols.length === 0 ? (
        <Text c="dimmed">Add the securities to compare, e.g. NVDA and MSFT.</Text>
      ) : (
        <div>
          <Group justify="space-between" align="flex-start" mb="sm">
            <Title order={2}>Price change</Title>
            <PeriodControls period={period} range={range} onChoose={choose} />
          </Group>
          {loaded.length === 0 && symbols.some((symbol) => closes[symbol]?.status !== "error") ? (
            <Skeleton h={CHART_HEIGHT} />
          ) : loaded.length > 0 ? (
            <TimeSeriesChart
              unit={PERCENT}
              shaded={false}
              points={changePoints(loaded)}
              series={symbols.map((symbol, index) => ({ name: symbol, label: symbol, color: COMPARISON_COLORS[index % COMPARISON_COLORS.length] }))}
              shown={symbols.filter((symbol) => !hidden.includes(symbol))}
              onShownChange={(shown) => setHidden(symbols.filter((symbol) => !shown.includes(symbol)))}
              onSelect={(start, end) => choose({ start, end })}
            />
          ) : null}
          <Text c="dimmed" size="sm" mt="xs">
            Each price&apos;s change since its first close in the period, adjusted for stock splits, so securities at any
            price compare. Dividends are not included.
          </Text>
          <Unavailable symbols={symbols} closes={closes} empty={isEverything(range) ? "" : ` ${describeRange(range)}`} />
        </div>
      )}
      {symbols.length > 0 && <SecuritiesSideBySide symbols={symbols} summaries={summaries} />}
    </Stack>
  );
}

/** The symbols compared, from the URL (?symbols=NVDA,MSFT), and a way to change them. */
function useComparedSymbols(): [string[], (symbols: string[]) => void] {
  const [params] = useSearchParams();
  const updateQuery = useUpdateQuery();
  const symbols = (params.get(COMPARED_SYMBOLS_PARAM) ?? "").split(COMPARED_SYMBOLS_SEPARATOR).filter(Boolean).slice(0, MAX_SYMBOLS);
  function choose(next: string[]) {
    updateQuery((current) => {
      const updated = new URLSearchParams(current);
      if (next.length === 0) {
        updated.delete(COMPARED_SYMBOLS_PARAM);
      } else {
        updated.set(COMPARED_SYMBOLS_PARAM, next.join(COMPARED_SYMBOLS_SEPARATOR));
      }
      return updated;
    });
  }
  return [symbols, choose];
}

/** Why a symbol has no line: its closes could not be fetched, or there are none in the period. */
function Unavailable({ symbols, closes, empty }: { symbols: string[]; closes: Record<string, ClosesState>; empty: string }) {
  return (
    <>
      {symbols.map((symbol) => {
        const state = closes[symbol];
        if (state?.status === "error") {
          return (
            <Alert key={symbol} color="yellow" mt="xs" title={`${symbol} unavailable`}>
              {state.message}
            </Alert>
          );
        }
        if (state?.status === "loaded" && state.closes.length === 0) {
          return (
            <Text key={symbol} c="dimmed" size="sm" mt="xs">
              No closing prices for {symbol}
              {empty}.
            </Text>
          );
        }
        return null;
      })}
    </>
  );
}

// For drawing only: the chart needs numbers. Prices stay exact strings everywhere else.
function changePoints(loaded: { symbol: string; closes: DailyCloseResponse[] }[]) {
  const byDay = new Map<string, Record<string, number | null>>();
  for (const { symbol, closes } of loaded) {
    const first = Number(closes[0].close);
    for (const { day, close } of closes) {
      byDay.set(day, { ...byDay.get(day), [symbol]: (Number(close) / first - 1) * PERCENT_FACTOR });
    }
  }
  return [...byDay.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([day, values]) => ({ day, ...values }));
}

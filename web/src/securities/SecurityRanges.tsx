import { Alert, Group, SimpleGrid, Skeleton, Text } from "@mantine/core";

import type { ValueRangeResponse } from "../api/generated";
import { formatAmount, formatDate, shortDecimal } from "../ui/format";
import { InfoTip } from "../ui/InfoTip";
import { RangeBar } from "../ui/RangeBar";
import { CHART_HEIGHT } from "../ui/theme";
import { EXPLANATIONS } from "./explanations";
import { useRanges } from "./useSecurity";

const CENT_PLACES = 2;

type Props = { symbol: string; start: string | null; end: string | null; currency: string | null };

/** Where the price and the P/E stand within their lows and highs over the chart's period. */
export function SecurityRanges({ symbol, start, end, currency }: Props) {
  const state = useRanges(symbol, start, end);
  if (state.status === "loading") {
    return <Skeleton h={CHART_HEIGHT / 4} />;
  }
  if (state.status === "error") {
    return (
      <Alert color="yellow" title="Ranges unavailable">
        {state.message}
      </Alert>
    );
  }
  const { price, pe } = state.ranges;
  // Split-adjusted prices can have more decimals than were traded: shown to the cent.
  const money = (value: string) => `${formatAmount(shortDecimal(value, CENT_PLACES))}${currency ? ` ${currency}` : ""}`;
  return (
    <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="xl">
      <RangeBlock title="Price range" explanation={EXPLANATIONS.priceRange} range={price} format={money} empty="No closing prices in this period." />
      <RangeBlock
        title="P/E range"
        explanation={EXPLANATIONS.peRange}
        range={pe}
        format={(value) => formatAmount(value)}
        empty="No P/E in this period: no positive EPS reported by then, or no fundamentals for this company."
      />
    </SimpleGrid>
  );
}

type BlockProps = { title: string; explanation: string; range: ValueRangeResponse | null; format: (value: string) => string; empty: string };

function RangeBlock({ title, explanation, range, format, empty }: BlockProps) {
  return (
    <div>
      <Group gap={4} wrap="nowrap">
        <Text c="dimmed" size="sm">
          {title}
        </Text>
        <InfoTip topic={title}>{explanation}</InfoTip>
      </Group>
      {range === null ? (
        <Text c="dimmed" size="sm">
          {empty}
        </Text>
      ) : (
        <>
          <Text c="dimmed" size="xs" mb={4}>
            {formatDate(range.start)} – {formatDate(range.end)}
          </Text>
          <RangeBar
            label={title}
            low={Number(range.low)}
            high={Number(range.high)}
            current={Number(range.current)}
            lowText={format(range.low)}
            highText={format(range.high)}
            currentText={format(range.current)}
          />
        </>
      )}
    </div>
  );
}

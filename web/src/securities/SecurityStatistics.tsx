import { Alert, Group, Skeleton, Text, Title } from "@mantine/core";

import { ReturnText } from "../ui/GainText";
import { Figure } from "../ui/Figure";
import { formatCompactAmount, formatPercent } from "../ui/format";
import { FIGURE_ROW_HEIGHT } from "../ui/theme";
import { EXPLANATIONS } from "./explanations";
import { useStatistics } from "./useSecurity";

type Props = { symbol: string; start: string | null; end: string | null; currency: string | null };

/** How the price has moved: its trend, and over the selected period how much it swings, its deepest fall and its beta. */
export function SecurityStatistics({ symbol, start, end, currency }: Props) {
  const state = useStatistics(symbol, start, end);
  return (
    <div>
      <Title order={3} mb="xs">
        Trend and risk
      </Title>
      <Text c="dimmed" size="sm" mb="sm">
        A description of the past, for context: none of these predicts what the price will do.
      </Text>
      {state.status === "loading" && <Skeleton h={FIGURE_ROW_HEIGHT} />}
      {state.status === "error" && (
        <Alert color="yellow" title="Trend and risk unavailable">
          {state.message}
        </Alert>
      )}
      {state.status === "loaded" && (
        <Group gap="xl" align="flex-start">
          <Figure label="3 months" explanation={EXPLANATIONS.trend}>
            <Change percent={state.statistics.three_month_return} />
          </Figure>
          <Figure label="6 months" explanation={EXPLANATIONS.trend}>
            <Change percent={state.statistics.six_month_return} />
          </Figure>
          <Figure label="1 year" explanation={EXPLANATIONS.trend}>
            <Change percent={state.statistics.one_year_return} />
          </Figure>
          <Figure label="Volatility" explanation={EXPLANATIONS.volatility} note="A year's worth, in the period">
            {state.statistics.volatility_percent == null ? "—" : `${formatPercent(state.statistics.volatility_percent)}%`}
          </Figure>
          <Figure label="Deepest fall" explanation={EXPLANATIONS.maxDrawdown} note="From a high, in the period">
            {state.statistics.max_drawdown_percent == null ? "—" : `${formatPercent(state.statistics.max_drawdown_percent)}%`}
          </Figure>
          <Figure label="Beta" explanation={EXPLANATIONS.beta} note={`Against ${state.statistics.benchmark_symbol}, in the period`}>
            {state.statistics.beta ?? "—"}
          </Figure>
          <Figure
            label="Daily volume"
            explanation={EXPLANATIONS.averageVolume}
            note={
              state.statistics.average_daily_value == null || currency == null
                ? "On average, in the period"
                : `${formatCompactAmount(state.statistics.average_daily_value)} ${currency} a day, on average`
            }
          >
            {state.statistics.average_daily_volume == null ? "—" : `${formatCompactAmount(state.statistics.average_daily_volume)} shares`}
          </Figure>
        </Group>
      )}
    </div>
  );
}

function Change({ percent }: { percent: string | null }) {
  return percent == null ? "—" : <ReturnText percent={percent} inherit />;
}

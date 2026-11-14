import { AreaChart } from "@mantine/charts";

import { formatAmount, formatDate, formatWholeAmount } from "./format";
import { CHART_HEIGHT } from "./theme";

export type ChartSeries = {
  name: string; // the key of its values in each point
  label: string;
  color: string; // a theme colour, e.g. "teal.6"
  dashed?: boolean; // for reference lines, e.g. money put in
};

type Props = {
  // Oldest first; `day` as YYYY-MM-DD. A null value is a day without one: the line has a gap there.
  points: ({ day: string } & Record<string, number | string | null>)[];
  series: ChartSeries[];
  currency: string;
};

// Room for the y axis's labels, e.g. "123,456", in px.
const Y_AXIS_WIDTH = 60;
// Dash pattern of reference lines.
const DASHED = "5 5";

/** Amounts over time, one point per day, with dates and amounts written as everywhere else in the app. */
export function TimeSeriesChart({ points, series, currency }: Props) {
  // The chart shows its x values as they are, so each point carries its date already formatted.
  const data = points.map((point) => ({ ...point, date: formatDate(point.day) }));
  return (
    <AreaChart
      h={CHART_HEIGHT}
      data={data}
      dataKey="date"
      series={series.map(({ name, label, color, dashed }) => ({ name, label, color, strokeDasharray: dashed ? DASHED : undefined }))}
      curveType="linear"
      connectNulls={false}
      withDots={false}
      withLegend
      fillOpacity={0.15}
      valueFormatter={(value) => `${formatAmount(value.toFixed(2))} ${currency}`}
      // The axis shows whole amounts without the currency, so its labels stay on one line; the tooltip has both.
      yAxisProps={{ domain: ["auto", "auto"], tickFormatter: formatWholeAmount, width: Y_AXIS_WIDTH }}
      xAxisProps={{ minTickGap: 40 }}
    />
  );
}

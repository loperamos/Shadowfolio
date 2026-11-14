import { AreaChart } from "@mantine/charts";
import { getThemeColor, useMantineTheme } from "@mantine/core";
import { useState } from "react";
import { type MouseHandlerDataParam, ReferenceArea } from "recharts";

import { formatAmount, formatDate, formatWholeAmount } from "./format";
import { CHART_HEIGHT, CHART_SELECTION_OPACITY } from "./theme";

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
  // Called with the first and last day (YYYY-MM-DD) of a drag across the chart; without it, the chart cannot be dragged.
  onSelect?: (first: string, last: string) => void;
};

// Room for the y axis's labels, e.g. "123,456", in px.
const Y_AXIS_WIDTH = 60;
// Dash pattern of reference lines.
const DASHED = "5 5";

/**
 * Amounts over time, one point per day, with dates and amounts written as everywhere else in the app. With `onSelect`,
 * dragging across it selects days, shaded while dragging (as zooming in Grafana and other time-series tools).
 */
export function TimeSeriesChart({ points, series, currency, onSelect }: Props) {
  const theme = useMantineTheme();
  // The chart shows its x values as they are, so each point carries its date already formatted.
  const data = points.map((point) => ({ ...point, date: formatDate(point.day) }));
  // Indexes of the points where a drag started and where it is now; null when not dragging.
  const [drag, setDrag] = useState<{ from: number; to: number } | null>(null);
  const indexOf = (state: MouseHandlerDataParam) => (state.activeTooltipIndex == null ? null : Number(state.activeTooltipIndex));

  function start(state: MouseHandlerDataParam) {
    const index = indexOf(state);
    setDrag(index === null ? null : { from: index, to: index });
  }
  function move(state: MouseHandlerDataParam) {
    const index = indexOf(state);
    if (drag !== null && index !== null) {
      setDrag({ ...drag, to: index });
    }
  }
  function end() {
    // A click, without dragging, selects nothing; either direction works.
    if (drag !== null && drag.from !== drag.to && onSelect) {
      onSelect(points[Math.min(drag.from, drag.to)].day, points[Math.max(drag.from, drag.to)].day);
    }
    setDrag(null);
  }

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
      areaChartProps={onSelect && { onMouseDown: start, onMouseMove: move, onMouseUp: end, onMouseLeave: () => setDrag(null) }}
    >
      {drag !== null && drag.from !== drag.to && (
        <ReferenceArea
          x1={data[drag.from].date}
          x2={data[drag.to].date}
          fill={getThemeColor(theme.primaryColor, theme)}
          fillOpacity={CHART_SELECTION_OPACITY}
        />
      )}
    </AreaChart>
  );
}

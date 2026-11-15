import { Anchor, Group, Loader, Table, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";
import { Link } from "react-router";

import type { SecuritySummaryResponse } from "../api/generated";
import { securityPath } from "../routes";
import { ReturnText } from "../ui/GainText";
import { InfoTip } from "../ui/InfoTip";
import { formatCompactAmount, formatDate, formatPercent } from "../ui/format";
import { TABLE_MIN_WIDTH } from "../ui/theme";
import { EXPLANATIONS } from "./explanations";
import type { SummaryState } from "./useSecurity";

type Row = { label: string; explanation: string; value: (summary: SecuritySummaryResponse) => ReactNode };
type RowGroup = { title: string; rows: Row[] };

const percent = (value: string | null | undefined) => (value == null ? null : `${formatPercent(value)}%`);
const change = (value: string | null | undefined) => (value == null ? null : <ReturnText percent={value} inherit />);
const money = (value: string | null | undefined, currency: string | null | undefined) =>
  value == null ? null : `${formatCompactAmount(value)}${currency ? ` ${currency}` : ""}`;
const day = (value: string | null | undefined) => (value == null ? null : formatDate(value));

// The measures compared, grouped as on the security page; each explained the same way.
const GROUPS: RowGroup[] = [
  {
    title: "Valuation",
    rows: [
      { label: "P/E", explanation: EXPLANATIONS.pe, value: (s) => s.pe },
      { label: "Price to sales", explanation: EXPLANATIONS.priceToSales, value: (s) => s.price_to_sales },
      { label: "FCF yield", explanation: EXPLANATIONS.freeCashFlowYield, value: (s) => percent(s.free_cash_flow_yield) },
      { label: "Market cap", explanation: EXPLANATIONS.marketCap, value: (s) => money(s.market_cap, s.currency) },
    ],
  },
  {
    title: "Growth and profit, last fiscal year",
    rows: [
      { label: "Revenue growth", explanation: EXPLANATIONS.revenueGrowth, value: (s) => change(s.revenue_growth) },
      { label: "Net margin", explanation: EXPLANATIONS.netMargin, value: (s) => percent(s.net_margin) },
    ],
  },
  {
    title: "Dividends",
    rows: [
      { label: "Dividend yield", explanation: EXPLANATIONS.dividendYield, value: (s) => percent(s.dividend_yield) },
      { label: "Next ex-dividend", explanation: EXPLANATIONS.exDividend, value: (s) => day(s.next_ex_dividend) },
    ],
  },
  {
    title: "Trend",
    rows: [
      { label: "3 months", explanation: EXPLANATIONS.trend, value: (s) => change(s.three_month_return) },
      { label: "6 months", explanation: EXPLANATIONS.trend, value: (s) => change(s.six_month_return) },
      { label: "1 year", explanation: EXPLANATIONS.trend, value: (s) => change(s.one_year_return) },
    ],
  },
  {
    title: "Risk, in the period",
    rows: [
      { label: "Volatility", explanation: EXPLANATIONS.volatility, value: (s) => percent(s.volatility) },
      { label: "Deepest fall", explanation: EXPLANATIONS.maxDrawdown, value: (s) => percent(s.max_drawdown) },
      { label: "Beta", explanation: EXPLANATIONS.beta, value: (s) => s.beta },
      { label: "Traded a day", explanation: EXPLANATIONS.averageVolume, value: (s) => money(s.average_daily_value, s.currency) },
    ],
  },
  {
    title: "Company",
    rows: [
      { label: "Industry", explanation: EXPLANATIONS.industry, value: (s) => s.industry },
      { label: "Next earnings", explanation: EXPLANATIONS.earnings, value: (s) => day(s.next_earnings) },
    ],
  },
];

/**
 * The securities' measures side by side: one column per security, one row per measure, in groups. No value is
 * marked best: whether a high P/E or yield is good depends on the company, which the explanations help judge.
 */
export function SecuritiesSideBySide({ symbols, summaries }: { symbols: string[]; summaries: Record<string, SummaryState> }) {
  const cell = (symbol: string, row: Row) => {
    const state = summaries[symbol];
    if (state === undefined || state.status === "loading") {
      return <Loader size="xs" />;
    }
    return state.status === "loaded" ? (row.value(state.summary) ?? "—") : "—";
  };
  return (
    <div>
      <Title order={2} mb="sm">
        Side by side
      </Title>
      <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
        <Table>
          <Table.Thead>
            <Table.Tr>
              <Table.Th />
              {symbols.map((symbol) => (
                <Table.Th key={symbol} ta="right">
                  <Anchor component={Link} to={securityPath(symbol)}>
                    {symbol}
                  </Anchor>
                </Table.Th>
              ))}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {GROUPS.map((group) => [
              <Table.Tr key={group.title}>
                <Table.Td colSpan={symbols.length + 1}>
                  <Text fw={600} size="sm" c="dimmed">
                    {group.title}
                  </Text>
                </Table.Td>
              </Table.Tr>,
              ...group.rows.map((row) => (
                <Table.Tr key={`${group.title}-${row.label}`}>
                  <Table.Td>
                    <Group gap={4} wrap="nowrap">
                      {row.label}
                      <InfoTip topic={row.label}>{row.explanation}</InfoTip>
                    </Group>
                  </Table.Td>
                  {symbols.map((symbol) => (
                    <Table.Td key={symbol} ta="right">
                      {cell(symbol, row)}
                    </Table.Td>
                  ))}
                </Table.Tr>
              )),
            ])}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {symbols.map((symbol) => {
        const state = summaries[symbol];
        const reasons = state?.status === "error" ? [state.message] : state?.status === "loaded" ? state.summary.unavailable : [];
        return reasons.map((reason) => (
          <Text key={`${symbol}-${reason}`} c="dimmed" size="sm" mt="xs">
            {symbol}: {reason}
          </Text>
        ));
      })}
    </div>
  );
}

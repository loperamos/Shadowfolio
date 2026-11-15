import { Alert, Group, Skeleton, Table, Text, Title } from "@mantine/core";

import { formatAmount, formatCompactAmount, formatDate } from "../ui/format";
import { CHART_HEIGHT, TABLE_MIN_WIDTH } from "../ui/theme";
import { useFundamentals } from "./useSecurity";

// The most recent fiscal years shown in the table.
const YEARS_SHOWN = 5;

/** What the company reported (yearly results, shares outstanding), with its P/E and market cap at the latest price. */
export function SecurityFundamentals({ symbol }: { symbol: string }) {
  const state = useFundamentals(symbol);
  return (
    <div>
      <Title order={2} mb="sm">
        Fundamentals
      </Title>
      <FundamentalsBody symbol={symbol} state={state} />
    </div>
  );
}

function FundamentalsBody({ symbol, state }: { symbol: string; state: ReturnType<typeof useFundamentals> }) {
  switch (state.status) {
    case "loading":
      return <Skeleton h={CHART_HEIGHT / 2} />;
    case "error":
      return (
        <Alert color="yellow" title="Fundamentals unavailable">
          {state.message}
        </Alert>
      );
    case "none":
      return <Text c="dimmed">No fundamentals for {symbol}: only companies that report to the US SEC are covered.</Text>;
    case "loaded": {
      const { company_name, currency, years, shares_outstanding, shares_as_of, pe, market_cap } = state.fundamentals;
      const latest = years.at(-1);
      const amount = (value: string | null | undefined) => (value == null ? "—" : `${formatCompactAmount(value)} ${currency}`);
      const figure = (label: string, value: string, note?: string) => (
        <div>
          <Text c="dimmed" size="sm">
            {label}
          </Text>
          <Text size="xl" fw={600}>
            {value}
          </Text>
          {note && (
            <Text c="dimmed" size="xs">
              {note}
            </Text>
          )}
        </div>
      );
      return (
        <>
          <Text mb="sm">{company_name}</Text>
          <Group gap="xl" mb="md">
            {figure("P/E", pe ?? "—", pe == null ? "No positive diluted EPS for the last fiscal year" : "Price against the last fiscal year's diluted EPS")}
            {figure("Market cap", amount(market_cap), market_cap == null ? "No single, recent share count (e.g. several share classes)" : undefined)}
            {figure("Shares outstanding", shares_outstanding == null ? "—" : formatCompactAmount(shares_outstanding), shares_as_of ? `As of ${formatDate(shares_as_of)}` : undefined)}
            {latest && figure("Revenue", amount(latest.revenue), `Fiscal year to ${formatDate(latest.end)}`)}
            {latest && figure("Net income", amount(latest.net_income), `Fiscal year to ${formatDate(latest.end)}`)}
          </Group>
          {years.length > 0 && (
            <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Fiscal year to</Table.Th>
                    <Table.Th ta="right">Revenue</Table.Th>
                    <Table.Th ta="right">Net income</Table.Th>
                    <Table.Th ta="right">EPS (diluted)</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {/* Newest first. */}
                  {years
                    .slice(-YEARS_SHOWN)
                    .reverse()
                    .map((year) => (
                      <Table.Tr key={year.end}>
                        <Table.Td>{formatDate(year.end)}</Table.Td>
                        <Table.Td ta="right">{amount(year.revenue)}</Table.Td>
                        <Table.Td ta="right">{amount(year.net_income)}</Table.Td>
                        <Table.Td ta="right">{year.eps_diluted == null ? "—" : `${formatAmount(year.eps_diluted)} ${currency}`}</Table.Td>
                      </Table.Tr>
                    ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
          <Text c="dimmed" size="sm" mt="xs">
            As reported to the US SEC in annual reports (10-K), through SEC EDGAR. EPS only for the years in the latest
            report: earlier ones are not restated for later stock splits.
          </Text>
        </>
      );
    }
  }
}

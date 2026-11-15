import { Alert, Group, Skeleton, Table, Text, Title } from "@mantine/core";

import { formatAmount, formatCompactAmount, formatDate, formatPercent } from "../ui/format";
import { ReturnText } from "../ui/GainText";
import { Figure } from "../ui/Figure";
import { InfoTip } from "../ui/InfoTip";
import { CHART_HEIGHT, TABLE_MIN_WIDTH } from "../ui/theme";
import { EXPLANATIONS } from "./explanations";
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
      const figure = (label: string, explanation: string, value: string, note?: string) => (
        <Figure label={label} explanation={explanation} note={note}>
          {value}
        </Figure>
      );
      return (
        <>
          <Text mb="sm">{company_name}</Text>
          {/* Top-aligned, so each label, value and note sits on the same line as the others'. */}
          <Group gap="xl" mb="md" align="flex-start">
            {figure("P/E", EXPLANATIONS.pe, pe ?? "—", pe == null ? "No positive diluted EPS for the last fiscal year" : "Price against the last fiscal year's diluted EPS")}
            {figure("Market cap", EXPLANATIONS.marketCap, amount(market_cap), market_cap == null ? "No single, recent share count (e.g. several share classes)" : undefined)}
            {figure("Shares outstanding", EXPLANATIONS.sharesOutstanding, shares_outstanding == null ? "—" : formatCompactAmount(shares_outstanding), shares_as_of ? `As of ${formatDate(shares_as_of)}` : undefined)}
            {latest && figure("Revenue", EXPLANATIONS.revenue, amount(latest.revenue), `Fiscal year to ${formatDate(latest.end)}`)}
            {latest && figure("Net income", EXPLANATIONS.netIncome, amount(latest.net_income), `Fiscal year to ${formatDate(latest.end)}`)}
          </Group>
          {years.length > 0 && (
            <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Fiscal year to</Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Revenue" explanation={EXPLANATIONS.revenue} />
                    </Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Growth" explanation={EXPLANATIONS.revenueGrowth} />
                    </Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Net income" explanation={EXPLANATIONS.netIncome} />
                    </Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Net margin" explanation={EXPLANATIONS.netMargin} />
                    </Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="EPS (diluted)" explanation={EXPLANATIONS.eps} />
                    </Table.Th>
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
                        <Table.Td ta="right">{year.revenue_growth == null ? "—" : <ReturnText percent={year.revenue_growth} />}</Table.Td>
                        <Table.Td ta="right">{amount(year.net_income)}</Table.Td>
                        <Table.Td ta="right">{year.net_margin == null ? "—" : `${formatPercent(year.net_margin)}%`}</Table.Td>
                        <Table.Td ta="right">{year.eps_diluted == null ? "—" : `${formatAmount(year.eps_diluted)} ${currency}`}</Table.Td>
                      </Table.Tr>
                    ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
          {years.length > 0 && (
            <>
              <Title order={3} mt="lg" mb="xs">
                Cash and debt
              </Title>
              <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Fiscal year to</Table.Th>
                      <Table.Th ta="right">
                        <HeaderWithInfo label="Operating cash flow" explanation={EXPLANATIONS.operatingCashFlow} />
                      </Table.Th>
                      <Table.Th ta="right">
                        <HeaderWithInfo label="Capital spending" explanation={EXPLANATIONS.capitalSpending} />
                      </Table.Th>
                      <Table.Th ta="right">
                        <HeaderWithInfo label="Free cash flow" explanation={EXPLANATIONS.freeCashFlow} />
                      </Table.Th>
                      <Table.Th ta="right">
                        <HeaderWithInfo label="Cash" explanation={EXPLANATIONS.cash} />
                      </Table.Th>
                      <Table.Th ta="right">
                        <HeaderWithInfo label="Debt" explanation={EXPLANATIONS.debt} />
                      </Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {/* Newest first, the same years as above. */}
                    {years
                      .slice(-YEARS_SHOWN)
                      .reverse()
                      .map((year) => (
                        <Table.Tr key={year.end}>
                          <Table.Td>{formatDate(year.end)}</Table.Td>
                          <Table.Td ta="right">{amount(year.operating_cash_flow)}</Table.Td>
                          <Table.Td ta="right">{amount(year.capital_spending)}</Table.Td>
                          <Table.Td ta="right">{amount(year.free_cash_flow)}</Table.Td>
                          <Table.Td ta="right">{amount(year.cash)}</Table.Td>
                          <Table.Td ta="right">{amount(year.debt)}</Table.Td>
                        </Table.Tr>
                      ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </>
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

/** A right-aligned column heading with its ⓘ. */
function HeaderWithInfo({ label, explanation }: { label: string; explanation: string }) {
  return (
    <Group gap={4} justify="flex-end" wrap="nowrap">
      {label}
      <InfoTip topic={label}>{explanation}</InfoTip>
    </Group>
  );
}

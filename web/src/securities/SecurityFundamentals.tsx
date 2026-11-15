import { Alert, Group, SegmentedControl, Skeleton, Table, Text, Title } from "@mantine/core";
import { useSearchParams } from "react-router";

import { formatAmount, formatCompactAmount, formatDate, formatPercent } from "../ui/format";
import { ReturnText } from "../ui/GainText";
import { Figure } from "../ui/Figure";
import { InfoTip } from "../ui/InfoTip";
import { CHART_HEIGHT, TABLE_MIN_WIDTH } from "../ui/theme";
import { useUpdateQuery } from "../ui/url";
import { EXPLANATIONS } from "./explanations";
import { useFundamentals } from "./useSecurity";

// The most recent fiscal years, or quarters (two years' worth), shown in the tables.
const YEARS_SHOWN = 5;
const QUARTERS_SHOWN = 8;

// Whether the tables show fiscal years or quarters, kept in the URL (?results=quarterly) when not the default.
enum ResultsView {
  YEARLY = "yearly",
  QUARTERLY = "quarterly",
}
const RESULTS_PARAM = "results";
const VIEW_OPTIONS = [
  { value: ResultsView.YEARLY, label: "Yearly" },
  { value: ResultsView.QUARTERLY, label: "Quarterly" },
];

function useResultsView(): [ResultsView, (view: ResultsView) => void] {
  const [params] = useSearchParams();
  const updateQuery = useUpdateQuery();
  const view = params.get(RESULTS_PARAM) === ResultsView.QUARTERLY ? ResultsView.QUARTERLY : ResultsView.YEARLY;
  function choose(next: ResultsView) {
    updateQuery((current) => {
      const updated = new URLSearchParams(current);
      if (next === ResultsView.YEARLY) {
        updated.delete(RESULTS_PARAM);
      } else {
        updated.set(RESULTS_PARAM, next);
      }
      return updated;
    });
  }
  return [view, choose];
}

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
  const [view, chooseView] = useResultsView();
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
      const { company_name, currency, years, quarters, shares_outstanding, shares_as_of, pe, market_cap, price_to_sales, free_cash_flow_yield } =
        state.fundamentals;
      const latest = years.at(-1);
      const quarterly = view === ResultsView.QUARTERLY;
      const periods = quarterly ? quarters.slice(-QUARTERS_SHOWN) : years.slice(-YEARS_SHOWN);
      const periodLabel = quarterly ? "Quarter to" : "Fiscal year to";
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
            {figure("Price to sales", EXPLANATIONS.priceToSales, price_to_sales ?? "—", price_to_sales == null ? undefined : "Market cap against the last fiscal year's revenue")}
            {figure(
              "FCF yield",
              EXPLANATIONS.freeCashFlowYield,
              free_cash_flow_yield == null ? "—" : `${formatPercent(free_cash_flow_yield)}%`,
              free_cash_flow_yield == null ? undefined : "Last fiscal year's free cash flow against the market cap",
            )}
            {figure("Market cap", EXPLANATIONS.marketCap, amount(market_cap), market_cap == null ? "No single, recent share count (e.g. several share classes)" : undefined)}
            {figure("Shares outstanding", EXPLANATIONS.sharesOutstanding, shares_outstanding == null ? "—" : formatCompactAmount(shares_outstanding), shares_as_of ? `As of ${formatDate(shares_as_of)}` : undefined)}
            {latest && figure("Revenue", EXPLANATIONS.revenue, amount(latest.revenue), `Fiscal year to ${formatDate(latest.end)}`)}
            {latest && figure("Net income", EXPLANATIONS.netIncome, amount(latest.net_income), `Fiscal year to ${formatDate(latest.end)}`)}
          </Group>
          <SegmentedControl
            mb="xs"
            aria-label="Yearly or quarterly results"
            data={VIEW_OPTIONS}
            value={view}
            onChange={(value) => chooseView(value as ResultsView)}
          />
          {periods.length === 0 && <Text c="dimmed">No {quarterly ? "quarterly" : "yearly"} results reported.</Text>}
          {periods.length > 0 && (
            <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
              <Table striped>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{periodLabel}</Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Revenue" explanation={EXPLANATIONS.revenue} />
                    </Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Growth" explanation={quarterly ? EXPLANATIONS.quarterRevenueGrowth : EXPLANATIONS.revenueGrowth} />
                    </Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Net income" explanation={EXPLANATIONS.netIncome} />
                    </Table.Th>
                    <Table.Th ta="right">
                      <HeaderWithInfo label="Net margin" explanation={EXPLANATIONS.netMargin} />
                    </Table.Th>
                    {!quarterly && (
                      <Table.Th ta="right">
                        <HeaderWithInfo label="EPS (diluted)" explanation={EXPLANATIONS.eps} />
                      </Table.Th>
                    )}
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {/* Newest first. */}
                  {[...periods]
                    .reverse()
                    .map((year) => (
                      <Table.Tr key={year.end}>
                        <Table.Td>{formatDate(year.end)}</Table.Td>
                        <Table.Td ta="right">{amount(year.revenue)}</Table.Td>
                        <Table.Td ta="right">{year.revenue_growth == null ? "—" : <ReturnText percent={year.revenue_growth} />}</Table.Td>
                        <Table.Td ta="right">{amount(year.net_income)}</Table.Td>
                        <Table.Td ta="right">{year.net_margin == null ? "—" : `${formatPercent(year.net_margin)}%`}</Table.Td>
                        {!quarterly && <Table.Td ta="right">{year.eps_diluted == null ? "—" : `${formatAmount(year.eps_diluted)} ${currency}`}</Table.Td>}
                      </Table.Tr>
                    ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          )}
          {periods.length > 0 && (
            <>
              <Title order={3} mt="lg" mb="xs">
                Cash and debt
              </Title>
              <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
                <Table striped>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>{periodLabel}</Table.Th>
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
                    {[...periods]
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
            As reported to the US SEC in annual (10-K) and quarterly (10-Q) reports, through SEC EDGAR; a quarter not
            reported on its own is worked out from the year to date. EPS only for the years in the latest annual report,
            and not by quarter: earlier ones are not restated for later stock splits.
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

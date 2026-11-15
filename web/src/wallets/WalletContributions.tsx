import { Anchor, Group, Table, Text, Title } from "@mantine/core";
import { Link } from "react-router";

import type { ContributionResponse } from "../api/generated";
import { securityPath } from "../routes";
import { GainText } from "../ui/GainText";
import { InfoTip } from "../ui/InfoTip";
import { Money } from "../ui/Money";
import { SortableTh } from "../ui/SortableTh";
import { sorted, SortOrder, useSort } from "../ui/sorting";
import { TABLE_MIN_WIDTH } from "../ui/theme";

// Columns the contributions can be sorted by; by default, the biggest gain first, as attribution reports list them.
enum ContributionColumn {
  SYMBOL = "symbol",
  START = "start",
  END = "end",
  GAIN = "gain",
}
const DEFAULT_SORT = { key: ContributionColumn.GAIN, order: SortOrder.DESCENDING };
// Its own sort parameters, as the holdings table on the same page has the plain ones.
const SORT_PREFIX = "drivers_";

type Props = {
  contributions: ContributionResponse[];
  otherGain: string | null;
  currency: string;
};

/** What each holding brought to the wallet's gain over the period, holdings sold in it included. */
export function WalletContributions({ contributions, otherGain, currency }: Props) {
  const [sort, sortBy] = useSort(Object.values(ContributionColumn), DEFAULT_SORT, SORT_PREFIX);
  const rows = sorted(contributions, valueIn(sort.key), sort.order);
  const th = (column: ContributionColumn, label: string, firstOrder = SortOrder.DESCENDING, align: "left" | "right" = "right") => (
    <SortableTh column={column} sort={sort} onSort={sortBy} firstOrder={firstOrder} align={align}>
      {label}
    </SortableTh>
  );
  return (
    <div>
      <Group gap={4} mt="lg" mb="xs" wrap="nowrap">
        <Title order={3}>What drove it</Title>
        <InfoTip topic="what drove it">
          Each holding's gain over the period: its value at the end, less its value at the start, plus what it paid in
          (sells, dividends) less what it cost (buys, fees). Together they make the wallet's gain; the rest, such as fees
          charged on their own, is under Other. The percentage is of the wallet's average value, so one lucky holding
          stands out from many small ones.
        </InfoTip>
      </Group>
      {rows.length === 0 ? (
        <Text c="dimmed">Nothing was held in this period.</Text>
      ) : (
        <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                {th(ContributionColumn.SYMBOL, "Symbol", SortOrder.ASCENDING, "left")}
                {th(ContributionColumn.START, "Value at start")}
                {th(ContributionColumn.END, "Value at end")}
                {th(ContributionColumn.GAIN, "Gain")}
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {rows.map((row) => (
                <Table.Tr key={row.symbol}>
                  <Table.Td>
                    <Anchor component={Link} to={securityPath(row.symbol)}>
                      {row.symbol}
                    </Anchor>
                  </Table.Td>
                  <Table.Td ta="right">
                    <Money amount={row.start_value} currency={currency} />
                  </Table.Td>
                  <Table.Td ta="right">
                    <Money amount={row.end_value} currency={currency} />
                  </Table.Td>
                  <Table.Td ta="right">
                    <GainText amount={row.gain} currency={currency} percent={row.gain_percent} />
                  </Table.Td>
                </Table.Tr>
              ))}
              {otherGain !== null && Number(otherGain) !== 0 && (
                <Table.Tr>
                  <Table.Td colSpan={3}>
                    <Text c="dimmed" inherit>
                      Other: fees charged on their own, interest, and the like
                    </Text>
                  </Table.Td>
                  <Table.Td ta="right">
                    <GainText amount={otherGain} currency={currency} />
                  </Table.Td>
                </Table.Tr>
              )}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
    </div>
  );
}

function valueIn(column: ContributionColumn) {
  return (row: ContributionResponse): number | string => {
    switch (column) {
      case ContributionColumn.SYMBOL:
        return row.symbol;
      case ContributionColumn.START:
        return Number(row.start_value);
      case ContributionColumn.END:
        return Number(row.end_value);
      case ContributionColumn.GAIN:
        return Number(row.gain);
    }
  };
}

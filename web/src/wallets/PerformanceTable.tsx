import { Table, Text } from "@mantine/core";
import type { ReactNode } from "react";

import type { PerformanceResponse } from "../api/generated";
import { GainText, ReturnText } from "../ui/GainText";

export type PerformanceColumn = {
  key: string;
  label: ReactNode;
  result: PerformanceResponse | null; // null: nothing to show (e.g. no prices), written as "—"
  currency: string; // of its gain
};

/** Gain and returns side by side, one column each (e.g. a wallet and its benchmark), each row saying what it measures. */
export function PerformanceTable({ columns }: { columns: PerformanceColumn[] }) {
  const row = (label: string, description: string, cell: (result: PerformanceResponse, currency: string) => ReactNode) => (
    <Table.Tr>
      <Table.Td>
        <Text inherit>{label}</Text>
        <Text c="dimmed" size="xs">
          {description}
        </Text>
      </Table.Td>
      {columns.map((column) => (
        <Table.Td key={column.key} ta="right">
          {column.result === null ? <Text c="dimmed">—</Text> : cell(column.result, column.currency)}
        </Table.Td>
      ))}
    </Table.Tr>
  );
  return (
    <Table>
      <Table.Thead>
        <Table.Tr>
          <Table.Th />
          {columns.map((column) => (
            <Table.Th key={column.key} ta="right">
              {column.label}
            </Table.Th>
          ))}
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {row("Gain", "End value less start value and money put in", (result, currency) => (
          <GainText amount={result.gain} currency={currency} />
        ))}
        {row("Return", "Time-weighted: what was held, whatever money moved", (result) => (
          <PerReturn total={result.time_weighted_return} perYear={result.time_weighted_return_per_year} />
        ))}
        {row("Return on your money", "Money-weighted: with when money went in and out", (result) =>
          result.money_weighted_return === null ? (
            <Text c="dimmed">—</Text>
          ) : (
            <PerReturn total={result.money_weighted_return} perYear={result.money_weighted_return_per_year} />
          ),
        )}
      </Table.Tbody>
    </Table>
  );
}

/** A return over the period, and per year when the period is a year or more. */
function PerReturn({ total, perYear }: { total: string; perYear: string | null }) {
  return (
    <>
      <ReturnText percent={total} />
      {perYear !== null && (
        <Text c="dimmed" size="xs">
          <ReturnText percent={perYear} suffix="a year" />
        </Text>
      )}
    </>
  );
}

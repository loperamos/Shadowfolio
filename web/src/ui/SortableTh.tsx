import { Group, Table, Text, UnstyledButton } from "@mantine/core";
import { IconChevronDown, IconChevronUp, IconSelector } from "@tabler/icons-react";
import type { ReactNode } from "react";

import { type Sort, SortOrder } from "./sorting";
import { ICON_SIZE } from "./theme";

type Props<K extends string> = {
  children: ReactNode;
  column: K;
  sort: Sort<K>;
  onSort: (key: K, firstOrder: SortOrder) => void;
  // The order a first click sorts in: largest first suits amounts, A to Z names.
  firstOrder: SortOrder;
  align?: "left" | "right";
};

/** A column header that sorts the table by its column (as in Mantine's sortable table): an arrow shows the order. */
export function SortableTh<K extends string>({ children, column, sort, onSort, firstOrder, align = "left" }: Props<K>) {
  const active = sort.key === column;
  const Icon = !active ? IconSelector : sort.order === SortOrder.ASCENDING ? IconChevronUp : IconChevronDown;
  const ariaSort = !active ? "none" : sort.order === SortOrder.ASCENDING ? "ascending" : "descending";
  return (
    <Table.Th ta={align} aria-sort={ariaSort}>
      <UnstyledButton onClick={() => onSort(column, firstOrder)}>
        <Group gap={4} wrap="nowrap" justify={align === "right" ? "flex-end" : "flex-start"}>
          <Text inherit fw="inherit">
            {children}
          </Text>
          <Icon size={ICON_SIZE} />
        </Group>
      </UnstyledButton>
    </Table.Th>
  );
}

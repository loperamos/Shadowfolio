import { Group, MultiSelect, Select } from "@mantine/core";
import { useState } from "react";

import { FILTER_INPUT_WIDTH } from "../ui/theme";
import type { OperationFilters } from "./operationFilters";

type Props = {
  filters: OperationFilters;
  types: { value: string; label: string }[];
  symbols: string[];
  onTypesChange: (types: string[]) => void;
  onSymbolChange: (symbol: string | null) => void;
};

/**
 * The operations' type and symbol filters. They show a choice at once, while the page (slower to draw) follows: a
 * second choice made before then still adds to the first.
 */
export function OperationFilterFields({ filters, types, symbols, onTypesChange, onSymbolChange }: Props) {
  const [chosen, setChosen] = useState(filters);
  // Follow changes made elsewhere (e.g. "Show all"), compared by content: `filters` is a new object on every draw.
  const [shownFilters, setShownFilters] = useState(filters);
  if (JSON.stringify(filters) !== JSON.stringify(shownFilters)) {
    setShownFilters(filters);
    setChosen(filters);
  }
  return (
    <Group gap="xs" align="flex-start">
      <MultiSelect
        size="xs"
        aria-label="Filter by type"
        placeholder={chosen.types.length === 0 ? "All types" : undefined}
        data={types}
        value={chosen.types}
        onChange={(next) => {
          setChosen({ ...chosen, types: next });
          onTypesChange(next);
        }}
        clearable
        w={FILTER_INPUT_WIDTH}
      />
      <Select
        size="xs"
        aria-label="Filter by symbol"
        placeholder="All symbols"
        data={symbols}
        value={chosen.symbol}
        onChange={(next) => {
          setChosen({ ...chosen, symbol: next });
          onSymbolChange(next);
        }}
        searchable
        clearable
        w={FILTER_INPUT_WIDTH}
      />
    </Group>
  );
}

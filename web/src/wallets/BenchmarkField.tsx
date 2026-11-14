import { Text, TextInput } from "@mantine/core";
import { useState } from "react";

import { SYMBOL_INPUT_WIDTH } from "../ui/theme";

/**
 * The benchmark to compare with: any symbol market data prices (e.g. QQQ, URTH). Applied on Enter or on leaving the
 * field, not on every letter; empty goes back to the default, shown as the placeholder.
 */
export function BenchmarkField({ symbol, placeholder, onChange }: { symbol: string | null; placeholder: string | null; onChange: (symbol: string | null) => void }) {
  const [text, setText] = useState(symbol ?? "");
  // Follow changes made elsewhere (e.g. a link), as the field keeps its own text while typing.
  const [shown, setShown] = useState(symbol);
  if (symbol !== shown) {
    setShown(symbol);
    setText(symbol ?? "");
  }
  const apply = () => text.trim().toUpperCase() !== (symbol ?? "") && onChange(text);
  return (
    <TextInput
      size="xs"
      aria-label="Compare with (symbol)"
      leftSection={<Text size="xs">vs</Text>}
      placeholder={placeholder ?? undefined}
      w={SYMBOL_INPUT_WIDTH}
      value={text}
      onChange={(event) => setText(event.currentTarget.value.toUpperCase())}
      onBlur={apply}
      onKeyDown={(event) => event.key === "Enter" && apply()}
    />
  );
}

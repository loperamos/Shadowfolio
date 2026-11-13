import { Text, type TextProps } from "@mantine/core";

import { formatAmount } from "./format";

// Keeps an amount and its currency on one line, so tables never split them.
export const NO_WRAP = { whiteSpace: "nowrap" } as const;

/** An amount in a currency, formatted the same way everywhere and never split across lines. */
export function Money({ amount, currency, ...textProps }: { amount: string; currency: string } & TextProps) {
  return (
    // Without a size, take the surrounding one (e.g. a table cell's), so amounts match the text around them.
    <Text span inherit={textProps.size === undefined} style={NO_WRAP} {...textProps}>
      {formatAmount(amount)} {currency}
    </Text>
  );
}

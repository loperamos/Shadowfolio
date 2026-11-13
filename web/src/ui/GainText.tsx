import { Text, type TextProps } from "@mantine/core";

type Props = {
  amount: string; // a decimal from the API; negative for a loss
  currency: string;
  percent?: string | null;
} & TextProps;

/** A gain or loss, written the same way everywhere: signed, coloured, with its percentage when there is one. */
export function GainText({ amount, currency, percent, ...textProps }: Props) {
  const direction = signOf(amount);
  const color = direction > 0 ? "teal" : direction < 0 ? "red" : "dimmed";
  return (
    <Text span c={color} {...textProps}>
      {signed(amount)} {currency}
      {percent != null && ` (${signed(percent)}%)`}
    </Text>
  );
}

/** "+68.63", "-12.40" or "0.00". */
function signed(value: string): string {
  return signOf(value) > 0 ? `+${value}` : value;
}

/** The sign of a decimal string, read from the text so money never goes through a float. */
function signOf(value: string): -1 | 0 | 1 {
  if (!/[1-9]/.test(value)) {
    return 0;
  }
  return value.trim().startsWith("-") ? -1 : 1;
}

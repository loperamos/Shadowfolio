import { Loader, Text, type TextProps, Tooltip } from "@mantine/core";

import type { ValuationState } from "./useWalletValuation";

/** A wallet's total value in its own currency; "—" with the reason on hover when it cannot be valued. */
export function WalletValue({ state, ...textProps }: { state: ValuationState } & TextProps) {
  switch (state.status) {
    case "loading":
      return <Loader size="xs" />;
    case "error":
      return (
        <Tooltip label={state.message}>
          <Text c="dimmed" {...textProps}>
            —
          </Text>
        </Tooltip>
      );
    case "loaded":
      return (
        <Text {...textProps}>
          {state.valuation.total} {state.valuation.currency}
        </Text>
      );
  }
}

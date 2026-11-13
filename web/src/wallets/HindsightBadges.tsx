import { Badge, Tooltip } from "@mantine/core";

import { TOOLTIP_WIDTH } from "../ui/theme";

// Badges keep their full size next to text that wraps (e.g. a long wallet name), instead of being cut short.
const KEEP_SIZE = { flexShrink: 0 } as const;

/** Marks a wallet whose results were built with hindsight, so they are not read as a forward test. */
export function HindsightBadge() {
  return (
    <Tooltip label="Some trades were priced from market data after the fact, so this wallet's results are not a forward test." multiline w={TOOLTIP_WIDTH}>
      <Badge color="yellow" variant="light" style={KEEP_SIZE}>
        Hindsight
      </Badge>
    </Tooltip>
  );
}

/** Marks a trade whose price was filled from market data rather than given by a broker. */
export function MarketPriceBadge() {
  return (
    <Tooltip label="Priced from market data: the first price traded at or after the trade's time." multiline w={TOOLTIP_WIDTH}>
      <Badge color="yellow" variant="light" style={KEEP_SIZE} size="xs">
        Market
      </Badge>
    </Tooltip>
  );
}

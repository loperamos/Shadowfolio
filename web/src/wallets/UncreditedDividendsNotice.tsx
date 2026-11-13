import { Alert, List } from "@mantine/core";

import type { WalletResponse } from "../api/generated";
import { formatDate } from "../ui/format";

/**
 * Lists dividends the wallet qualified for but that were not credited, because the market-data provider has no
 * payment date for them (dividends before about April 2020). Shows nothing when there are none.
 */
export function UncreditedDividendsNotice({ wallet }: { wallet: WalletResponse }) {
  const dividends = wallet.uncredited_dividends;
  if (dividends.length === 0) {
    return null;
  }
  return (
    <Alert color="gray" mb="lg" title={`${dividends.length} ${dividends.length === 1 ? "dividend was" : "dividends were"} not credited`}>
      The market-data provider has no payment date for {dividends.length === 1 ? "it" : "them"}, so when the cash arrived is unknown. Your
      broker’s statement has the actual payments.
      <List size="sm" mt="xs">
        {dividends.map((dividend) => (
          <List.Item key={`${dividend.symbol}-${dividend.ex_date}`}>
            {dividend.symbol}, ex-date {formatDate(dividend.ex_date)}: {dividend.per_share} {dividend.currency} a share
          </List.Item>
        ))}
      </List>
    </Alert>
  );
}

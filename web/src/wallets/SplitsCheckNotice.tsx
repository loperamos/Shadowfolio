import { Alert } from "@mantine/core";

import type { WalletResponse } from "../api/generated";
import { formatDate } from "../ui/format";

/**
 * Says when the wallet's holdings may miss a recent split, because their corporate actions are not checked through
 * today yet (the daily sync has not run since). Shows nothing when everything is up to date.
 */
export function SplitsCheckNotice({ wallet }: { wallet: WalletResponse }) {
  if (Object.keys(wallet.holdings).length === 0) {
    return null;
  }
  const checkedThrough = wallet.splits_checked_through;
  const today = new Date().toISOString().slice(0, 10); // the backend checks by UTC day
  if (checkedThrough != null && checkedThrough >= today) {
    return null;
  }
  return (
    <Alert color="gray" mb="lg">
      {checkedThrough == null
        ? "Splits have not been checked yet for some holdings. They are applied by the daily sync, or when you add a trade in them."
        : `Splits are checked through ${formatDate(checkedThrough)}. A split since then is applied by the next daily sync.`}
    </Alert>
  );
}

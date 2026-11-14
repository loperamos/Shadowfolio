// The frontend's URLs. The API lives under /api, so these never collide with it.
export const WALLETS_PATH = "/wallets";
export const WALLET_PATH = "/wallets/:walletId";

export function walletPath(walletId: string): string {
  return `${WALLETS_PATH}/${walletId}`;
}

// Wallets side by side: /compare?wallets=<id>,<id>.
export const COMPARE_PATH = "/compare";
export const COMPARED_WALLETS_PARAM = "wallets";
export const COMPARED_WALLETS_SEPARATOR = ",";

export function comparePath(walletIds: string[]): string {
  const query = new URLSearchParams({ [COMPARED_WALLETS_PARAM]: walletIds.join(COMPARED_WALLETS_SEPARATOR) });
  return `${COMPARE_PATH}?${query.toString()}`;
}

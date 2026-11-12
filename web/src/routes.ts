// The frontend's URLs. The API lives under /api, so these never collide with it.
export const WALLETS_PATH = "/wallets";
export const WALLET_PATH = "/wallets/:walletId";

export function walletPath(walletId: string): string {
  return `${WALLETS_PATH}/${walletId}`;
}

// The frontend's URLs. The API lives under /api, so these never collide with it.
export const WALLETS_PATH = "/wallets";
export const WALLET_PATH = "/wallets/:walletId";

export function walletPath(walletId: string): string {
  return `${WALLETS_PATH}/${walletId}`;
}

// A security's page, e.g. /securities/NVDA: its price and the wallets that hold it.
export const SECURITIES_PATH = "/securities";
export const SECURITY_PATH = "/securities/:symbol";

export function securityPath(symbol: string): string {
  return `${SECURITIES_PATH}/${encodeURIComponent(symbol)}`;
}

// Wallets side by side: /compare?wallets=<id>,<id>.
export const COMPARE_PATH = "/compare";
export const COMPARED_WALLETS_PARAM = "wallets";
export const COMPARED_WALLETS_SEPARATOR = ",";

export function comparePath(walletIds: string[]): string {
  const query = new URLSearchParams({ [COMPARED_WALLETS_PARAM]: walletIds.join(COMPARED_WALLETS_SEPARATOR) });
  return `${COMPARE_PATH}?${query.toString()}`;
}

// Securities side by side: /securities/compare?symbols=NVDA,MSFT. A static path, so it wins over a security's page.
export const SECURITIES_COMPARE_PATH = `${SECURITIES_PATH}/compare`;
export const COMPARED_SYMBOLS_PARAM = "symbols";
export const COMPARED_SYMBOLS_SEPARATOR = ",";

export function securitiesComparePath(symbols: string[]): string {
  const query = new URLSearchParams({ [COMPARED_SYMBOLS_PARAM]: symbols.join(COMPARED_SYMBOLS_SEPARATOR) });
  return `${SECURITIES_COMPARE_PATH}?${query.toString()}`;
}

import { DataProvider } from "../api/generated";

/** What the Settings page says about each market-data provider a user brings their own key for. */
export type ProviderInfo = {
  name: string;
  usedFor: string; // what Shadowfolio fetches with the key
  withoutIt: string; // what stops when the key is removed
  howToGet: string; // the steps on the provider's site
  signUpUrl: string;
  keyIdLabel?: string; // providers whose keys come in two parts (a key id and a secret)
  secretLabel: string;
};

export const PROVIDERS: Record<DataProvider, ProviderInfo> = {
  [DataProvider.ALPACA]: {
    name: "Alpaca",
    usedFor: "Prices, price history, dividends, splits and news: for your wallets, their orders and the securities you look up.",
    withoutIt: "Your wallets get no new prices, dividends or splits, and their orders do not fill, until you connect a key again.",
    howToGet:
      "Sign up for free, then generate an API key from the paper trading dashboard. Paper keys are enough: Shadowfolio only reads market data, never your account or trades.",
    signUpUrl: "https://app.alpaca.markets/signup",
    keyIdLabel: "API key ID",
    secretLabel: "Secret key",
  },
  [DataProvider.FINNHUB]: {
    name: "Finnhub",
    usedFor: "When companies report their results next, on security pages.",
    withoutIt: "Security pages show no earnings dates until you connect a key again.",
    howToGet: "Sign up for free; your API key is on your dashboard.",
    signUpUrl: "https://finnhub.io/register",
    secretLabel: "API key",
  },
};

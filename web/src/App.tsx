import { useEffect, useState } from "react";

import { listWallets, type WalletResponse } from "./api/generated";

export function App() {
  const [wallets, setWallets] = useState<WalletResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listWallets()
      .then(({ data }) => (data ? setWallets(data) : setError("Could not load wallets.")))
      .catch(() => setError("Could not reach the backend."));
  }, []);

  return (
    <main>
      <h1>Shadowfolio</h1>
      <WalletList wallets={wallets} error={error} />
    </main>
  );
}

function WalletList({ wallets, error }: { wallets: WalletResponse[] | null; error: string | null }) {
  if (error) {
    return <p>{error}</p>;
  }
  if (wallets === null) {
    return <p>Loading…</p>;
  }
  if (wallets.length === 0) {
    return <p>No wallets yet.</p>;
  }
  return (
    <ul>
      {wallets.map((wallet) => (
        <li key={wallet.id}>
          <strong>{wallet.name}</strong>: {wallet.cash} {wallet.currency} cash
          {Object.keys(wallet.holdings).length > 0 && (
            <ul>
              {Object.entries(wallet.holdings).map(([symbol, quantity]) => (
                <li key={symbol}>
                  {symbol}: {quantity} shares
                </li>
              ))}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}

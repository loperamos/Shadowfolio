import { Alert, Container, Loader, Table, Text, Title } from "@mantine/core";
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
    <Container py="xl">
      <Title order={1} mb="lg">
        Shadowfolio
      </Title>
      <WalletList wallets={wallets} error={error} />
    </Container>
  );
}

function WalletList({ wallets, error }: { wallets: WalletResponse[] | null; error: string | null }) {
  if (error) {
    return <Alert color="red">{error}</Alert>;
  }
  if (wallets === null) {
    return <Loader />;
  }
  if (wallets.length === 0) {
    return <Text c="dimmed">No wallets yet.</Text>;
  }
  return (
    <Table striped highlightOnHover>
      <Table.Thead>
        <Table.Tr>
          <Table.Th>Name</Table.Th>
          <Table.Th ta="right">Cash</Table.Th>
          <Table.Th>Holdings</Table.Th>
        </Table.Tr>
      </Table.Thead>
      <Table.Tbody>
        {wallets.map((wallet) => (
          <Table.Tr key={wallet.id}>
            <Table.Td>{wallet.name}</Table.Td>
            <Table.Td ta="right">
              {wallet.cash} {wallet.currency}
            </Table.Td>
            <Table.Td>
              {Object.entries(wallet.holdings)
                .map(([symbol, quantity]) => `${symbol} ${quantity}`)
                .join(", ") || <Text c="dimmed">None</Text>}
            </Table.Td>
          </Table.Tr>
        ))}
      </Table.Tbody>
    </Table>
  );
}

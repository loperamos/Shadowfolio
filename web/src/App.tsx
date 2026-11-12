import { Button, Container, Group, Title } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useCallback, useEffect, useState } from "react";

import { listWallets, type WalletResponse } from "./api/generated";
import { CreateWalletModal } from "./wallets/CreateWalletModal";
import { WalletTable } from "./wallets/WalletTable";

export function App() {
  const [wallets, setWallets] = useState<WalletResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, { open: openCreate, close: closeCreate }] = useDisclosure(false);

  const loadWallets = useCallback(() => {
    listWallets()
      .then(({ data }) => (data ? setWallets(data) : setError("Could not load wallets.")))
      .catch(() => setError("Could not reach the backend."));
  }, []);

  useEffect(loadWallets, [loadWallets]);

  return (
    <Container py="xl">
      <Group justify="space-between" mb="lg">
        <Title order={1}>Shadowfolio</Title>
        <Button onClick={openCreate}>New wallet</Button>
      </Group>
      <WalletTable wallets={wallets} error={error} />
      <CreateWalletModal opened={creating} onClose={closeCreate} onCreated={loadWallets} />
    </Container>
  );
}

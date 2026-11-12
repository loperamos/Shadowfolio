import { Anchor, Container, Stack, Text, Title } from "@mantine/core";
import { Link, Navigate, Route, Routes } from "react-router";

import { WALLET_PATH, WALLETS_PATH } from "./routes";
import { WalletPage } from "./wallets/WalletPage";
import { WalletsPage } from "./wallets/WalletsPage";

export function App() {
  return (
    <Container py="xl">
      <Routes>
        <Route path="/" element={<Navigate to={WALLETS_PATH} replace />} />
        <Route path={WALLETS_PATH} element={<WalletsPage />} />
        <Route path={WALLET_PATH} element={<WalletPage />} />
        <Route path="*" element={<PageNotFound />} />
      </Routes>
    </Container>
  );
}

function PageNotFound() {
  return (
    <Stack>
      <Title order={1}>Page not found</Title>
      <Text>
        <Anchor component={Link} to={WALLETS_PATH}>
          Back to your wallets
        </Anchor>
      </Text>
    </Stack>
  );
}

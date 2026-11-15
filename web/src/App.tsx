import { Anchor, Container, Stack, Text, Title } from "@mantine/core";
import { Link, Navigate, Route, Routes } from "react-router";

import { AppHeader } from "./AppHeader";
import { COMPARE_PATH, SECURITIES_COMPARE_PATH, SECURITY_PATH, WALLET_PATH, WALLETS_PATH } from "./routes";
import { SecuritiesComparePage } from "./securities/SecuritiesComparePage";
import { SecurityPage } from "./securities/SecurityPage";
import { ComparePage } from "./wallets/ComparePage";
import { WalletPage } from "./wallets/WalletPage";
import { WalletsPage } from "./wallets/WalletsPage";

export function App() {
  return (
    <Container size="xl" py="xl">
      <AppHeader />
      <Routes>
        <Route path="/" element={<Navigate to={WALLETS_PATH} replace />} />
        <Route path={WALLETS_PATH} element={<WalletsPage />} />
        <Route path={WALLET_PATH} element={<WalletPage />} />
        <Route path={COMPARE_PATH} element={<ComparePage />} />
        <Route path={SECURITIES_COMPARE_PATH} element={<SecuritiesComparePage />} />
        <Route path={SECURITY_PATH} element={<SecurityPage />} />
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

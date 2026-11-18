import { Anchor, Container, Group, Stack, Text, Title } from "@mantine/core";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { WALLETS_PATH } from "../routes";
import { Wordmark } from "../ui/Logo";
import { LOGO_HEADER_SIZE } from "../ui/theme";
import { PublicFooter } from "./PublicFooter";
import { LEGAL_UPDATED } from "./site";

/** A public page about using Shadowfolio (terms, privacy): readable width, the site's header and footer. */
export function LegalPage({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Container size="md" py="xl">
      <Group justify="space-between" mb="xl">
        <Anchor component={Link} to="/" underline="never" aria-label="Shadowfolio: home">
          <Wordmark size={LOGO_HEADER_SIZE} />
        </Anchor>
        <Anchor component={Link} to={WALLETS_PATH} fw={500}>
          Sign in
        </Anchor>
      </Group>
      <Stack gap="md">
        <Title order={1}>{title}</Title>
        <Text c="dimmed">Last updated {LEGAL_UPDATED}</Text>
        {children}
      </Stack>
      <PublicFooter />
    </Container>
  );
}

/** One section of a legal page. */
export function LegalSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Stack gap="xs" mt="md">
      <Title order={2}>{title}</Title>
      {children}
    </Stack>
  );
}

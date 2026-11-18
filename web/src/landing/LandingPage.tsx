import { Anchor, Button, Card, Container, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconArrowRight, IconChartHistogram, IconRobot, IconWallet } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { WALLETS_PATH } from "../routes";
import { Logo, Wordmark } from "../ui/Logo";
import { ICON_SIZE, LANDING_ICON_SIZE, LOGO_HERO_SIZE, LOGO_HEADER_SIZE } from "../ui/theme";

const FEATURES: { icon: ReactNode; title: string; text: string }[] = [
  {
    icon: <IconWallet size={LANDING_ICON_SIZE} />,
    title: "Your wallets, mirrored",
    text: "Import your broker's history (DEGIRO today) or start fresh. See value, returns against the market, risk and fees, day by day, all priced from real market data.",
  },
  {
    icon: <IconChartHistogram size={LANDING_ICON_SIZE} />,
    title: "Decide with context",
    text: "Each company's results, cash and debt, valuation, trend and risk, and securities side by side, with every figure explained in plain words.",
  },
  {
    icon: <IconRobot size={LANDING_ICON_SIZE} />,
    title: "Bring your own agent",
    text: "Connect Claude, Codex or any MCP client to read your wallets and place orders now, within the rules you set: no hindsight, judged on what comes next.",
  },
];

/** The public front page: what Shadowfolio is, and the way into the app (which asks to sign in). */
export function LandingPage() {
  const openApp = (
    <Button component={Link} to={WALLETS_PATH} size="md" rightSection={<IconArrowRight size={ICON_SIZE} />}>
      Open the app
    </Button>
  );
  return (
    <Container size="lg" py="xl">
      <Group justify="space-between" mb="xl">
        <Wordmark size={LOGO_HEADER_SIZE} />
        <Anchor component={Link} to={WALLETS_PATH} fw={500}>
          Sign in
        </Anchor>
      </Group>

      <Stack align="center" gap="lg" py="xl" ta="center">
        <Logo size={LOGO_HERO_SIZE} />
        <Title order={1}>Your investments, simulated with real market data</Title>
        <Text size="xl" c="dimmed" maw={720}>
          Mirror your broker&apos;s wallets, try decisions without risking money, and see what would have happened, all
          priced from real prices.
        </Text>
        {openApp}
        <Text size="sm" c="dimmed">
          Invite only for now.
        </Text>
      </Stack>

      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg" py="xl">
        {FEATURES.map((feature) => (
          <Card key={feature.title} withBorder padding="lg">
            <ThemeIcon size="xl" variant="light">
              {feature.icon}
            </ThemeIcon>
            <Title order={3} mt="md" mb="xs">
              {feature.title}
            </Title>
            <Text c="dimmed">{feature.text}</Text>
          </Card>
        ))}
      </SimpleGrid>

      <Text size="sm" c="dimmed" ta="center" mt="xl">
        Shadowfolio simulates: it never connects to a brokerage account or places real orders. Not investment advice.
        Market data from Alpaca; company filings from SEC EDGAR.
      </Text>
    </Container>
  );
}

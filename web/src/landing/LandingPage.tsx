import { Anchor, Badge, Button, Card, Code, Container, Group, SimpleGrid, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconArrowRight, IconChecklist, IconRobot, IconScale } from "@tabler/icons-react";
import type { ReactNode } from "react";
import { Link } from "react-router";

import { WALLETS_PATH } from "../routes";
import { Logo, Wordmark } from "../ui/Logo";
import { ICON_SIZE, LANDING_ICON_SIZE, LOGO_HEADER_SIZE, LOGO_HERO_SIZE } from "../ui/theme";

const FEATURES: { icon: ReactNode; title: string; text: string }[] = [
  {
    icon: <IconRobot size={LANDING_ICON_SIZE} />,
    title: "Bring your own agent",
    text: "Claude, Codex or any MCP client reads your wallets and the market, and places orders, with a token that only reaches the wallets you grant it.",
  },
  {
    icon: <IconChecklist size={LANDING_ICON_SIZE} />,
    title: "Rules it can't break",
    text: "The largest a position may grow, the cash to keep, the symbols it may buy, how often it may trade: every order is checked, and refused with the reason.",
  },
  {
    icon: <IconScale size={LANDING_ICON_SIZE} />,
    title: "Judged honestly",
    text: "Orders happen now, at the next real price: never back-dated with hindsight. Each keeps its reason, and how it did against the market since.",
  },
];

const STEPS: { title: string; text: string; code?: string }[] = [
  { title: "Create a wallet", text: "Start with cash, or import your broker's history to mirror what you already own." },
  { title: "Set its rules and a token", text: "Choose the limits it trades within, and create a token for the agent: read only, or trading." },
  {
    title: "Connect your agent",
    text: "Give it the token, e.g. with Claude Code:",
    code: 'claude mcp add --transport http \\\n  shadowfolio <this site>/mcp \\\n  --header "Authorization: Bearer <token>"',
  },
];

/** The public front page: what Shadowfolio is (a portfolio your own AI agent manages, safely), and the way into the
 * app, which asks to sign in. */
export function LandingPage() {
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
        <Title order={1}>Let your AI agent manage a portfolio</Title>
        <Text size="xl" c="dimmed" maw={720}>
          With real market data, within the rules you set, and never with real money: see how its decisions would have
          done before you trust it with yours.
        </Text>
        <Button component={Link} to={WALLETS_PATH} size="md" rightSection={<IconArrowRight size={ICON_SIZE} />}>
          Open the app
        </Button>
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

      <Title order={2} ta="center" mt="xl" mb="lg">
        How it works
      </Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="lg">
        {STEPS.map((step, index) => (
          <Stack key={step.title} gap="xs">
            <Group gap="xs">
              <Badge size="lg" circle>
                {index + 1}
              </Badge>
              <Text fw={600}>{step.title}</Text>
            </Group>
            <Text c="dimmed">{step.text}</Text>
            {step.code && <Code block>{step.code}</Code>}
          </Stack>
        ))}
      </SimpleGrid>

      <Text c="dimmed" ta="center" maw={720} mx="auto" mt="xl" pt="xl">
        And you see everything it sees: each wallet&apos;s value, returns against the market, risk and fees, with every
        figure explained, and each company&apos;s results, valuation and trend, side by side.
      </Text>

      <Text size="sm" c="dimmed" ta="center" mt="xl">
        Shadowfolio simulates: it never connects to a brokerage account or places real orders. Not investment advice.
        Market data from Alpaca; company filings from SEC EDGAR.
      </Text>
    </Container>
  );
}

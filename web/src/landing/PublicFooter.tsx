import { Anchor, Group, Stack, Text } from "@mantine/core";
import { Link } from "react-router";

import { PRIVACY_PATH, TERMS_PATH } from "../routes";
import { CONTACT_EMAIL } from "./site";

/** The footer of the public pages: what Shadowfolio is not, where its data comes from, and the terms and privacy. */
export function PublicFooter() {
  return (
    <Stack gap="xs" align="center" ta="center" mt="xl" pt="xl">
      <Text size="sm" c="dimmed">
        Shadowfolio simulates: it never connects to a brokerage account or places real orders. Not investment advice.
      </Text>
      <Text size="sm" c="dimmed">
        Market data from your own Alpaca and Finnhub accounts; company filings from SEC EDGAR; exchange rates from the
        European Central Bank.
      </Text>
      <Group gap="md" justify="center">
        <Anchor component={Link} to={TERMS_PATH} size="sm">
          Terms
        </Anchor>
        <Anchor component={Link} to={PRIVACY_PATH} size="sm">
          Privacy
        </Anchor>
        <Anchor href={`mailto:${CONTACT_EMAIL}`} size="sm">
          {CONTACT_EMAIL}
        </Anchor>
      </Group>
    </Stack>
  );
}

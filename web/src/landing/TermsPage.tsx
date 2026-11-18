import { Anchor, List, Text } from "@mantine/core";
import { Link } from "react-router";

import { PRIVACY_PATH } from "../routes";
import { LegalPage, LegalSection } from "./LegalPage";
import { CONTACT_EMAIL } from "./site";

/** The terms of use, in plain words: a free showcase that simulates, with no guarantees. */
export function TermsPage() {
  return (
    <LegalPage title="Terms of use">
      <Text>
        Shadowfolio is a free, personal, non-commercial project: a showcase of what an AI agent can do with a simulated
        portfolio. By signing in you agree to these terms.
      </Text>
      <LegalSection title="It simulates">
        <Text>
          Shadowfolio never connects to a brokerage account and never places real orders: every wallet, order and trade
          is simulated, priced with market data. Nothing on it is investment, financial, tax or legal advice, and how a
          simulated wallet did says nothing certain about what real money would do.
        </Text>
      </LegalSection>
      <LegalSection title="No guarantees">
        <Text>
          It is provided as it is, without any warranty. Prices and figures may be late, wrong or missing; features may
          change; the service may stop, and data may be lost. As far as the law allows, its owner is not liable for any
          loss from using it.
        </Text>
      </LegalSection>
      <LegalSection title="Your keys and your agents">
        <List spacing="xs">
          <List.Item>
            Market data comes from your own accounts at Alpaca and Finnhub, with the keys you save. You are responsible
            for those accounts and for following their providers&apos; terms. What your keys fetch is only shown to you.
          </List.Item>
          <List.Item>
            Your agents act with the access tokens you create: you are responsible for what they do with them. Revoke a
            token to stop an agent at once.
          </List.Item>
        </List>
      </LegalSection>
      <LegalSection title="Fair use">
        <Text>
          Each plan has limits (wallets, orders a day, agent tokens, requests a minute) so the service stays available to
          everyone. Do not try to get around them, overload the service or reach other people&apos;s data. Accounts that
          do may be suspended or deleted.
        </Text>
      </LegalSection>
      <LegalSection title="Your data">
        <Text>
          How your data is kept, and how to delete it, is in the{" "}
          <Anchor component={Link} to={PRIVACY_PATH} inherit>
            privacy notice
          </Anchor>
          . You can delete your account at any time from Settings.
        </Text>
      </LegalSection>
      <LegalSection title="Changes and contact">
        <Text>
          These terms may change; the date above says when they last did. Questions:{" "}
          <Anchor href={`mailto:${CONTACT_EMAIL}`} inherit>
            {CONTACT_EMAIL}
          </Anchor>
          .
        </Text>
      </LegalSection>
    </LegalPage>
  );
}

import { Anchor, List, Text } from "@mantine/core";

import { LegalPage, LegalSection } from "./LegalPage";
import { CONTACT_EMAIL } from "./site";

/** The privacy notice, in plain words: what is kept, who else is involved, for how long, and how to delete it. */
export function PrivacyPage() {
  const contact = (
    <Anchor href={`mailto:${CONTACT_EMAIL}`} inherit>
      {CONTACT_EMAIL}
    </Anchor>
  );
  return (
    <LegalPage title="Privacy notice">
      <Text>
        Shadowfolio is a free, personal, non-commercial project run by one person, who decides what is done with your
        data. Write to {contact} about anything here.
      </Text>
      <LegalSection title="What is kept">
        <List spacing="xs">
          <List.Item>
            Your sign-in id, as the sign-in provider gives it (e.g. google-oauth2|1005…), and when you first signed in.
            Your name and email are shown to you from your sign-in, but not stored.
          </List.Item>
          <List.Item>
            What you create: your wallets, their history, orders and rules. A broker statement you import is read into
            operations; the file itself is not kept.
          </List.Item>
          <List.Item>Your agents&apos; access tokens, only as a one-way hash: the tokens themselves are not kept.</List.Item>
          <List.Item>Your market-data keys, encrypted.</List.Item>
          <List.Item>
            How much you use the service, per day: requests made, and calls made with your keys to each provider. Used to
            keep within limits and to see what the service costs; never sold or shared.
          </List.Item>
        </List>
      </LegalSection>
      <LegalSection title="Who else is involved">
        <List spacing="xs">
          <List.Item>Auth0 (by Okta) signs you in, and Google if you sign in with Google.</List.Item>
          <List.Item>Cloudflare carries the traffic to the server.</List.Item>
          <List.Item>
            Alpaca and Finnhub receive the requests made with your keys (e.g. which symbols to price), as they would from
            any app you gave your keys to.
          </List.Item>
          <List.Item>SEC EDGAR, the European Central Bank and OpenFIGI receive requests for public data, without anything about you.</List.Item>
        </List>
        <Text>There are no ads, no analytics and no tracking cookies; your sign-in is kept by Auth0 in your browser.</Text>
      </LegalSection>
      <LegalSection title="How long, and how to delete it">
        <Text>
          Your data is kept until you delete your account, from Settings: that deletes your wallets, tokens, keys and
          usage at once. Nightly backups are kept for 14 days, so deleted data is gone from them within two weeks.
          Signing in again afterwards starts a new, empty account.
        </Text>
      </LegalSection>
      <LegalSection title="Your rights">
        <Text>
          You can ask for a copy of your data, have it corrected or deleted, or object to how it is used, by writing to{" "}
          {contact}. If you are in the European Union, you can also complain to your data protection authority.
        </Text>
      </LegalSection>
    </LegalPage>
  );
}

import { Alert, Badge, Button, Card, Group, Loader, Stack, Text, Title } from "@mantine/core";
import { useCallback, useEffect, useState } from "react";

import { apiErrorMessage } from "../api/errors";

import { DataProvider, type KeyCheckResponse, listProviderKeys, type ProviderKeyResponse, testProviderKey } from "../api/generated";
import { formatDateTime } from "../ui/format";
import { ExternalLink } from "../ui/ExternalLink";
import { PROVIDERS } from "./providers";
import { RemoveKeyModal } from "./RemoveKeyModal";
import { SaveKeyModal } from "./SaveKeyModal";

/**
 * The user's settings: their own market-data keys, one card per provider as GitHub and Vercel list connected services:
 * what the key is for, how to get one, and whether one is connected (by its last characters only).
 */
export function SettingsPage() {
  const [keys, setKeys] = useState<ProviderKeyResponse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toSave, setToSave] = useState<DataProvider | null>(null);
  const [toRemove, setToRemove] = useState<DataProvider | null>(null);
  const [testing, setTesting] = useState<DataProvider | null>(null);
  const [checks, setChecks] = useState<Partial<Record<DataProvider, KeyCheckResponse>>>({});

  const load = useCallback(() => {
    setChecks({}); // a replaced or removed key's last test no longer applies
    listProviderKeys()
      .then(({ data }) => (data ? setKeys(data) : setError("Could not load your keys.")))
      .catch(() => setError("Could not reach the backend."));
  }, []);
  useEffect(load, [load]);

  const saved = (provider: DataProvider) => keys?.find((key) => key.provider === provider) ?? null;

  async function test(provider: DataProvider) {
    setTesting(provider);
    try {
      const { data, error } = await testProviderKey({ path: { provider } });
      setChecks((current) => ({ ...current, [provider]: data ?? { works: false, message: apiErrorMessage(error) } }));
    } catch {
      setChecks((current) => ({ ...current, [provider]: { works: false, message: "Could not reach the backend." } }));
    } finally {
      setTesting(null);
    }
  }

  return (
    <Stack gap="lg">
      <Title order={1}>Settings</Title>
      <div>
        <Title order={2}>Market data keys</Title>
        <Text c="dimmed" mt="xs">
          Shadowfolio fetches market data with your own free accounts at these providers. Keys are stored encrypted and
          used only for you: what they fetch is never shown to anyone else.
        </Text>
      </div>
      {error && <Alert color="red">{error}</Alert>}
      {keys === null && !error && <Loader size="sm" />}
      {keys !== null &&
        Object.values(DataProvider).map((provider) => {
          const info = PROVIDERS[provider];
          const key = saved(provider);
          return (
            <Card key={provider} withBorder padding="lg">
              <Group justify="space-between" align="flex-start" wrap="nowrap">
                <Stack gap="xs">
                  <Group gap="sm">
                    <Title order={3}>{info.name}</Title>
                    {key ? <Badge variant="light">Connected</Badge> : <Badge color="gray" variant="light">Not connected</Badge>}
                  </Group>
                  <Text>{info.usedFor}</Text>
                  <Text size="sm" c="dimmed">
                    {info.howToGet}{" "}
                    <ExternalLink href={info.signUpUrl}>Get a key from {info.name}</ExternalLink>
                  </Text>
                  {key && (
                    <Text size="sm">
                      Key ending <Text span ff="monospace">{key.hint}</Text>, saved {formatDateTime(key.saved_at)}
                    </Text>
                  )}
                  {/* Announced when it appears, as the answer to pressing Test. */}
                  <div role="status">
                    {key && checks[provider] && (
                      <Text size="sm" c={checks[provider].works ? "teal" : "red"} fw={500}>
                        {checks[provider].message}
                      </Text>
                    )}
                  </div>
                </Stack>
                <Group gap="xs" wrap="nowrap">
                  {key && (
                    <Button variant="default" loading={testing === provider} onClick={() => test(provider)}>
                      Test
                    </Button>
                  )}
                  <Button variant={key ? "default" : "filled"} onClick={() => setToSave(provider)}>
                    {key ? "Replace" : "Connect"}
                  </Button>
                  {key && (
                    <Button color="red" variant="light" onClick={() => setToRemove(provider)}>
                      Remove
                    </Button>
                  )}
                </Group>
              </Group>
            </Card>
          );
        })}
      <SaveKeyModal provider={toSave} replacing={toSave !== null && saved(toSave) !== null} onClose={() => setToSave(null)} onSaved={load} />
      <RemoveKeyModal provider={toRemove} onClose={() => setToRemove(null)} onRemoved={load} />
    </Stack>
  );
}

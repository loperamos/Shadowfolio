import { Alert, Badge, Button, Group, Loader, Stack, Table, Text, Title, Tooltip } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconPlus } from "@tabler/icons-react";
import { useCallback, useEffect, useState } from "react";

import { type AccessTokenResponse, listAccessTokens, listWallets, Scope, type WalletResponse } from "../api/generated";
import { formatDateTime } from "../ui/format";
import { ICON_SIZE, TABLE_MIN_WIDTH } from "../ui/theme";
import { CreateTokenModal } from "./CreateTokenModal";
import { RevokeTokenModal } from "./RevokeTokenModal";

export const SCOPE_LABELS: Record<Scope, string> = { [Scope.READ]: "Read", [Scope.TRADING]: "Trading" };
const SCOPE_COLORS: Record<Scope, string> = { [Scope.READ]: "blue", [Scope.TRADING]: "orange" };

type Loaded = { tokens: AccessTokenResponse[]; wallets: WalletResponse[] };

/**
 * The access tokens agents use with the MCP server, as GitHub and Stripe list their tokens and keys: what each is for,
 * its scope and wallets, when it was last used; create one (its secret shown once), or revoke one.
 */
export function AgentAccessPage() {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, { open: openCreate, close: closeCreate }] = useDisclosure(false);
  const [toRevoke, setToRevoke] = useState<AccessTokenResponse | null>(null);

  const load = useCallback(() => {
    Promise.all([listAccessTokens(), listWallets()])
      .then(([tokens, wallets]) => {
        if (tokens.data && wallets.data) {
          setLoaded({ tokens: tokens.data, wallets: wallets.data });
        } else {
          setError("Could not load the access tokens.");
        }
      })
      .catch(() => setError("Could not reach the backend."));
  }, []);
  useEffect(load, [load]);

  const walletName = (id: string) => loaded?.wallets.find((wallet) => wallet.id === id)?.name ?? "A deleted wallet";
  const noWallets = loaded !== null && loaded.wallets.length === 0;
  const create = (
    <Button leftSection={<IconPlus size={ICON_SIZE} />} onClick={openCreate} disabled={loaded === null || noWallets}>
      Create token
    </Button>
  );

  return (
    <Stack gap="lg">
      <div>
        <Group justify="space-between" align="flex-start">
          <Title order={1}>Agent access</Title>
          {noWallets ? <Tooltip label="Create a wallet first: a token needs one to use.">{create}</Tooltip> : create}
        </Group>
        <Text c="dimmed" mt="xs">
          Tokens let agents (Claude Code, Codex and other MCP clients) use your wallets through Shadowfolio&apos;s MCP
          server. Each sees only the wallets you grant it.
        </Text>
      </div>
      {error && <Alert color="red">{error}</Alert>}
      {loaded === null && !error && <Loader />}
      {loaded !== null && loaded.tokens.length === 0 && <Text c="dimmed">No tokens yet. Create one to connect an agent.</Text>}
      {loaded !== null && loaded.tokens.length > 0 && (
        <Table.ScrollContainer minWidth={TABLE_MIN_WIDTH}>
          <Table>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Name</Table.Th>
                <Table.Th>Scope</Table.Th>
                <Table.Th>Wallets</Table.Th>
                <Table.Th>Created</Table.Th>
                <Table.Th>Last used</Table.Th>
                <Table.Th />
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {[...loaded.tokens].reverse().map((token) => {
                const revoked = token.revoked_at != null;
                return (
                  <Table.Tr key={token.id}>
                    <Table.Td>
                      <Text c={revoked ? "dimmed" : undefined} inherit>
                        {token.name}
                      </Text>
                      <Text c="dimmed" size="xs" ff="monospace">
                        {token.hint}…
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={revoked ? "gray" : SCOPE_COLORS[token.scope]} variant="light">
                        {SCOPE_LABELS[token.scope]}
                      </Badge>
                    </Table.Td>
                    <Table.Td>{token.wallet_ids.map(walletName).join(", ")}</Table.Td>
                    <Table.Td>{formatDateTime(token.created_at)}</Table.Td>
                    <Table.Td>{token.last_used_at ? formatDateTime(token.last_used_at) : "Never"}</Table.Td>
                    <Table.Td ta="right">
                      {revoked ? (
                        <Tooltip label={`Revoked ${formatDateTime(token.revoked_at as string)}: it no longer works.`}>
                          <Badge color="gray" variant="outline">
                            Revoked
                          </Badge>
                        </Tooltip>
                      ) : (
                        <Button size="xs" variant="subtle" color="red" onClick={() => setToRevoke(token)}>
                          Revoke
                        </Button>
                      )}
                    </Table.Td>
                  </Table.Tr>
                );
              })}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Text c="dimmed" size="sm">
        Give an agent its token as a header, &quot;Authorization: Bearer &lt;token&gt;&quot;, with the MCP server&apos;s
        address: /mcp on the backend (see the README). A read token sees its wallets and previews orders; a trading token
        also places and cancels orders, now only, within each wallet&apos;s rules.
      </Text>
      {loaded && <CreateTokenModal opened={creating} wallets={loaded.wallets} onClose={closeCreate} onCreated={load} />}
      <RevokeTokenModal token={toRevoke} onClose={() => setToRevoke(null)} onRevoked={load} />
    </Stack>
  );
}

import { Anchor, Avatar, Button, CopyButton, Group, Menu, Text, TextInput } from "@mantine/core";
import { IconCopy, IconLogout, IconSearch } from "@tabler/icons-react";
import { type FormEvent, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router";

import { AGENTS_PATH, SECURITIES_COMPARE_PATH, securityPath, WALLETS_PATH } from "./routes";
import { useAuth } from "./auth/useAuth";
import { ICON_SIZE, SEARCH_INPUT_WIDTH } from "./ui/theme";

/**
 * The header on every page: the app's name, its sections, and a symbol lookup that opens any security's page (as on
 * finance sites, where a security is reached from the header rather than from inside a section).
 */
export function AppHeader() {
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState("");

  function lookUp(event: FormEvent) {
    event.preventDefault();
    const wanted = symbol.trim().toUpperCase();
    if (wanted) {
      setSymbol("");
      navigate(securityPath(wanted));
    }
  }

  return (
    <Group justify="space-between" mb="xl">
      <Group gap="lg">
        <Anchor component={Link} to={WALLETS_PATH} c="inherit" underline="never">
          <Text fw={700} size="lg">
            Shadowfolio
          </Text>
        </Anchor>
        {/* The current section reads as active (aria-current), as NavLink marks it. */}
        <Anchor component={NavLink} to={WALLETS_PATH} fw={500}>
          Wallets
        </Anchor>
        <Anchor component={NavLink} to={SECURITIES_COMPARE_PATH} fw={500}>
          Compare securities
        </Anchor>
        <Anchor component={NavLink} to={AGENTS_PATH} fw={500}>
          Agent access
        </Anchor>
      </Group>
      <Group gap="md">
        <form onSubmit={lookUp} role="search">
          <TextInput
            aria-label="Look up a symbol"
            placeholder="Look up a symbol, e.g. NVDA"
            leftSection={<IconSearch size={ICON_SIZE} />}
            w={SEARCH_INPUT_WIDTH}
            value={symbol}
            onChange={(event) => setSymbol(event.currentTarget.value)}
          />
        </form>
        <UserMenu />
      </Group>
    </Group>
  );
}

/** Who is signed in, with their user id to copy (it owns their wallets) and signing out. */
function UserMenu() {
  const { user, signOut } = useAuth();
  return (
    <Menu position="bottom-end" withinPortal>
      <Menu.Target>
        <Button variant="subtle" color="gray" leftSection={<Avatar name={user.name} color="initials" size="sm" />}>
          {user.name}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        {user.email && <Menu.Label>{user.email}</Menu.Label>}
        <CopyButton value={user.id}>
          {({ copied, copy }) => (
            <Menu.Item leftSection={<IconCopy size={ICON_SIZE} />} onClick={copy} closeMenuOnClick={false}>
              {copied ? "Copied" : "Copy user id"}
              <Text c="dimmed" size="xs" ff="monospace">
                {user.id}
              </Text>
            </Menu.Item>
          )}
        </CopyButton>
        <Menu.Divider />
        <Menu.Item leftSection={<IconLogout size={ICON_SIZE} />} onClick={signOut}>
          Sign out
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}

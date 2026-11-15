import { Anchor, Group, Text, TextInput } from "@mantine/core";
import { IconSearch } from "@tabler/icons-react";
import { type FormEvent, useState } from "react";
import { Link, NavLink, useNavigate } from "react-router";

import { securityPath, WALLETS_PATH } from "./routes";
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
      </Group>
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
    </Group>
  );
}

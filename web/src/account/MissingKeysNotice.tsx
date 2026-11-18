import { Alert, Anchor, Text } from "@mantine/core";
import { IconKey } from "@tabler/icons-react";
import { Link, useLocation } from "react-router";

import { SETTINGS_PATH } from "../routes";
import { PROVIDERS } from "../settings/providers";
import { ICON_SIZE } from "../ui/theme";
import { useMe } from "./plan";

/**
 * Asks the user to connect the market-data keys they still need, on every page but Settings (where they connect them),
 * as a banner that says what is missing and links to where to fix it. Checked again on each page, so it goes once done.
 */
export function MissingKeysNotice() {
  const { pathname } = useLocation();
  const me = useMe(pathname);
  const missing = me?.missing_keys ?? [];
  if (missing.length === 0 || pathname === SETTINGS_PATH) {
    return null;
  }
  const names = missing.map((provider) => PROVIDERS[provider].name).join(" and ");
  return (
    <Alert color="yellow" icon={<IconKey size={ICON_SIZE} />} title={`Connect your ${names} key`} mb="lg">
      <Text size="sm">
        Prices, dividends and news come from your own free {names} account, so nothing shows until you connect its key.{" "}
        <Anchor component={Link} to={SETTINGS_PATH} inherit fw={500}>
          Go to Settings
        </Anchor>
      </Text>
    </Alert>
  );
}

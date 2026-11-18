import { Anchor } from "@mantine/core";
import { IconExternalLink } from "@tabler/icons-react";
import type { ReactNode } from "react";

import { ICON_SIZE } from "./theme";

/** A link to another site, opened in a new tab, with the icon that says so (for screen readers too). */
export function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Anchor href={href} target="_blank" rel="noopener noreferrer" inherit>
      {children} <IconExternalLink size={ICON_SIZE} aria-label="(opens in a new tab)" style={{ verticalAlign: "middle" }} />
    </Anchor>
  );
}

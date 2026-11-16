import { ActionIcon, Code, CopyButton, Group, Tooltip } from "@mantine/core";
import { IconCheck, IconCopy } from "@tabler/icons-react";

import { ICON_SIZE } from "./theme";

/** A secret shown once (e.g. an access token), in full, with a button that copies it and says so. */
export function SecretValue({ value, label }: { value: string; label: string }) {
  return (
    <Group gap="xs" wrap="nowrap">
      <Code block style={{ flex: 1, wordBreak: "break-all" }}>
        {value}
      </Code>
      <CopyButton value={value}>
        {({ copied, copy }) => (
          <Tooltip label={copied ? "Copied" : "Copy"} withArrow>
            <ActionIcon variant={copied ? "filled" : "default"} onClick={copy} aria-label={`Copy ${label}`} size="lg">
              {copied ? <IconCheck size={ICON_SIZE} /> : <IconCopy size={ICON_SIZE} />}
            </ActionIcon>
          </Tooltip>
        )}
      </CopyButton>
    </Group>
  );
}

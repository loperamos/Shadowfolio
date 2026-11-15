import { Group, Text } from "@mantine/core";
import type { ReactNode } from "react";

import { InfoTip } from "./InfoTip";

/** A labelled figure, e.g. a P/E or a wallet's cash share: a dimmed label with its ⓘ, the value, and an optional note. */
export function Figure({ label, explanation, note, children }: { label: string; explanation: string; note?: string; children: ReactNode }) {
  return (
    <div>
      <Group gap={4} wrap="nowrap">
        <Text c="dimmed" size="sm">
          {label}
        </Text>
        <InfoTip topic={label}>{explanation}</InfoTip>
      </Group>
      <Text size="xl" fw={600}>
        {children}
      </Text>
      {note && (
        <Text c="dimmed" size="xs">
          {note}
        </Text>
      )}
    </div>
  );
}

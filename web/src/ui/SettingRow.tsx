import { Box, Group, Stack, Text } from "@mantine/core";
import type { ReactNode } from "react";

type Props = {
  id: string; // the control's id, so the name labels it; its description gets `${id}-description`
  label: string;
  description: string;
  children: ReactNode; // the control, e.g. a short input
  wide?: boolean; // the control goes under the text, across the whole width (e.g. a list of symbols)
};

/**
 * One setting in a settings list: name and description on the left, its control on the right, in a single row; or,
 * for a control that needs the room, under them.
 */
export function SettingRow({ id, label, description, children, wide = false }: Props) {
  const text = (
    <Stack gap={2}>
      <Text component="label" htmlFor={id} size="sm" fw={500}>
        {label}
      </Text>
      <Text id={settingDescriptionId(id)} size="xs" c="dimmed">
        {description}
      </Text>
    </Stack>
  );
  if (wide) {
    return (
      <Stack gap="xs">
        {text}
        {children}
      </Stack>
    );
  }
  return (
    <Group justify="space-between" align="flex-start" wrap="nowrap">
      {text}
      {/* Keeps its own width; the text wraps around it instead. */}
      <Box flex="none">{children}</Box>
    </Group>
  );
}

/** The id of a setting's description, for the control's aria-describedby. */
export function settingDescriptionId(id: string): string {
  return `${id}-description`;
}

import { ActionIcon, Tooltip } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";

import { ICON_SIZE, TOOLTIP_WIDTH } from "./theme";

/**
 * A small ⓘ next to a label that explains it: shown on hover, on keyboard focus and on touch, and read out by screen
 * readers as "About <topic>".
 */
export function InfoTip({ topic, children }: { topic: string; children: string }) {
  return (
    <Tooltip label={children} multiline w={TOOLTIP_WIDTH} events={{ hover: true, focus: true, touch: true }} withArrow>
      <ActionIcon variant="subtle" color="gray" size="xs" aria-label={`About ${topic}`}>
        <IconInfoCircle size={ICON_SIZE} />
      </ActionIcon>
    </Tooltip>
  );
}

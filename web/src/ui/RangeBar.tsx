import { Box, Group, Text, useMantineTheme } from "@mantine/core";

import { RANGE_BAR_HEIGHT, RANGE_DOT_SIZE } from "./theme";

type Props = {
  label: string; // what the values are, e.g. "Price", for screen readers
  low: number;
  high: number;
  current: number;
  // The values as written on the page, exact (e.g. "147.00 USD").
  lowText: string;
  highText: string;
  currentText: string;
};

/**
 * Where a value stands between its low and its high (e.g. a price within its range over a period): a bar with a dot
 * at the current value, as finance sites show a 52-week range. Read out as a meter by screen readers.
 */
export function RangeBar({ label, low, high, current, lowText, highText, currentText }: Props) {
  const theme = useMantineTheme();
  // Where the dot sits along the bar, from 0 to 100; in the middle when the range is a single value.
  const position = high > low ? ((current - low) / (high - low)) * 100 : 50;
  return (
    <div>
      <Text size="sm" fw={600} mb={4}>
        {currentText}
      </Text>
      <Box
        role="meter"
        aria-label={`${label}: ${currentText}, between ${lowText} and ${highText}`}
        aria-valuemin={low}
        aria-valuemax={high}
        aria-valuenow={current}
        pos="relative"
        h={RANGE_BAR_HEIGHT}
        bg={theme.colors.gray[3]}
        style={{ borderRadius: theme.radius.xl }}
      >
        <Box
          pos="absolute"
          top="50%"
          w={RANGE_DOT_SIZE}
          h={RANGE_DOT_SIZE}
          bg={theme.colors[theme.primaryColor][6]}
          style={{ left: `${position}%`, transform: "translate(-50%, -50%)", borderRadius: "50%" }}
        />
      </Box>
      <Group justify="space-between" mt={4}>
        <Text c="dimmed" size="xs">
          {lowText}
        </Text>
        <Text c="dimmed" size="xs">
          {highText}
        </Text>
      </Group>
    </div>
  );
}

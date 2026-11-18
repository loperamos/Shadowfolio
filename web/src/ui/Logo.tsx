import { Group, Text } from "@mantine/core";

// The mark's drawing, on a 64-unit square: a rising line, and its shadow below and to the right (the market, and the
// wallet that mirrors it). The colours are the theme's primary teal; public/favicon.svg is the same drawing.
const LINE = "13,44 25,32 33,38 51,18";
const SHADOW_OFFSET = "translate(3,4)";

/** Shadowfolio's mark, `size` pixels square. Decorative: the name beside it, or its label, says what it is. */
export function Logo({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="var(--mantine-color-teal-6)" />
      <polyline
        points={LINE}
        fill="none"
        stroke="var(--mantine-color-teal-9)"
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
        transform={SHADOW_OFFSET}
        opacity="0.6"
      />
      <polyline points={LINE} fill="none" stroke="var(--mantine-color-white)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** The mark with the name, as in the header. */
export function Wordmark({ size }: { size: number }) {
  return (
    <Group gap="xs" wrap="nowrap">
      <Logo size={size} />
      <Text fw={700} size="lg" c="var(--mantine-color-text)">
        Shadowfolio
      </Text>
    </Group>
  );
}

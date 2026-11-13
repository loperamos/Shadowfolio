// The app's single theme. Colours, spacing, typography and radii are set here and nowhere else;
// components take them from the theme (see AGENTS.md, Frontend).
import { createTheme, rem } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "teal",
  defaultRadius: "md",
  fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
});

// Size of icons inside buttons and menus, in px.
export const ICON_SIZE = 16;

// Widths of inputs whose content always has the same length, so they don't stretch across a form.
export const DATE_INPUT_WIDTH = rem(128); // the calendar icon, DD/MM/YYYY and the usual inner padding
export const TIME_INPUT_WIDTH = rem(78); // HH:mm and the usual inner padding

// Below this width, tables scroll sideways instead of squeezing their columns.
export const TABLE_MIN_WIDTH = rem(900);

// Width of tooltips that hold a sentence, so they wrap into a readable block.
export const TOOLTIP_WIDTH = rem(260);

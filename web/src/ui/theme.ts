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
export const DATE_INPUT_WIDTH = rem(150); // DD/MM/YYYY plus the calendar icon
export const TIME_INPUT_WIDTH = rem(90); // HH:mm

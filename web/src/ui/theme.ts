// The app's single theme. Colours, spacing, typography and radii are set here and nowhere else;
// components take them from the theme (see AGENTS.md, Frontend).
import { createTheme } from "@mantine/core";

export const theme = createTheme({
  primaryColor: "teal",
  defaultRadius: "md",
  fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
});

// Size of icons inside buttons and menus, in px.
export const ICON_SIZE = 16;

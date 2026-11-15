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
export const PERCENT_INPUT_WIDTH = rem(110); // up to 99.99 and the % sign
export const COUNT_INPUT_WIDTH = rem(110); // a whole number of a few digits, or a short placeholder
// Width of a search field above a list: room for a name, without stretching across the page.
export const SEARCH_INPUT_WIDTH = rem(260);
// Width of a field for a ticker symbol, e.g. a benchmark's.
export const SYMBOL_INPUT_WIDTH = rem(120);
// Width of a filter above a list (e.g. by type), room for a couple of choices before they wrap.
export const FILTER_INPUT_WIDTH = rem(200);

// Colours of the wallets drawn side by side in a comparison, in order (theme colours; repeated past the last).
export const COMPARISON_COLORS = ["teal.6", "orange.6", "grape.6", "cyan.6", "red.6", "lime.7"];

// A range bar's track height and its dot's size, in px.
export const RANGE_BAR_HEIGHT = 6;
export const RANGE_DOT_SIZE = 14;

// Height of time-series charts, in px.
export const CHART_HEIGHT = 280;
// How strongly the days being selected by dragging across a chart are shaded (0 to 1).
export const CHART_SELECTION_OPACITY = 0.15;

// Tallest a list inside a dialog grows before it scrolls (e.g. an import's problems), in px.
export const DIALOG_LIST_MAX_HEIGHT = 240;

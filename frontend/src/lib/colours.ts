/** Label colours from the theme (src/index.css, --label-*). Text on them is white. */
export const LABEL_COLOURS = [
  "grey",
  "green",
  "amber",
  "red",
  "blue",
  "purple",
  "pink",
  "teal",
  "orange",
  "lime",
  "indigo",
  "brown",
] as const;

export type LabelColour = (typeof LABEL_COLOURS)[number];

export function labelColour(colour: string | null | undefined): string {
  return `var(--label-${LABEL_COLOURS.includes(colour as LabelColour) ? colour : "grey"})`;
}

/** Series colours for charts that have no label colour of their own. */
// Fixed order, checked with the dataviz validator for colour-blind separation in both themes.
const SERIES = [
  "blue",
  "orange",
  "green",
  "purple",
  "teal",
  "red",
  "indigo",
  "pink",
  "amber",
  "lime",
  "brown",
  "grey",
];

export function seriesColour(index: number, colour?: string | null): string {
  return colour ? labelColour(colour) : labelColour(SERIES[index % SERIES.length]);
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (
    ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() ||
    "?"
  );
}

/** A steady colour per person, for avatars. */
export function personColour(id: number): string {
  return labelColour(SERIES[id % (SERIES.length - 1)]);
}

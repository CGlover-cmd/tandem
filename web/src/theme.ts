// Design tokens: every colour the window uses, for light and dark mode, plus the window
// backgrounds the user can pick in Settings. `applyTheme` writes them as CSS variables
// (HeroUI's own names where it has one), and theme.test.ts checks text contrast (WCAG AA)
// against every background, so a new colour can't quietly fail it.

export type Mode = "light" | "dark";

export interface Palette {
  foreground: string;
  muted: string; // secondary text
  accent: string; // filled buttons
  accentForeground: string;
  accentText: string; // accent-coloured text and focus rings
  success: string;
  warning: string;
  danger: string;
  glass: string; // translucent card surface, rgba
  sheet: string; // sheets and popovers, nearly opaque
  hairline: string;
  scrim: string;
  shadow: string;
  field: string;
}

export const palettes: Record<Mode, Palette> = {
  light: {
    foreground: "#1D1D1F",
    muted: "#5E5E63",
    accent: "#0066CC",
    accentForeground: "#FFFFFF",
    accentText: "#005EBD",
    success: "#1E7A34",
    warning: "#A84B00",
    danger: "#C8001A",
    glass: "rgba(255, 255, 255, 0.68)",
    sheet: "rgba(255, 255, 255, 0.92)",
    hairline: "rgba(0, 0, 0, 0.08)",
    scrim: "rgba(0, 0, 0, 0.18)",
    shadow: "rgba(26, 31, 51, 0.12)",
    field: "rgba(0, 0, 0, 0.05)",
  },
  dark: {
    foreground: "#F5F5F7",
    muted: "#A8A8AD",
    accent: "#0071E3",
    accentForeground: "#FFFFFF",
    accentText: "#6CB6FF",
    success: "#30D158",
    warning: "#FF9F0A",
    danger: "#FF7B73",
    glass: "rgba(44, 44, 46, 0.62)",
    sheet: "rgba(36, 36, 38, 0.94)",
    hairline: "rgba(255, 255, 255, 0.10)",
    scrim: "rgba(0, 0, 0, 0.45)",
    shadow: "rgba(0, 0, 0, 0.45)",
    field: "rgba(255, 255, 255, 0.08)",
  },
};

export interface Background {
  id: string;
  label: string;
  group: "neutral" | "gradient";
  stops: Record<Mode, string[]>;
}

// Ids must match tandem.ui.backend.BACKGROUNDS.
export const backgrounds: Background[] = [
  {
    id: "mist",
    label: "Mist",
    group: "neutral",
    stops: { light: ["#F5F5F7", "#E8E8ED"], dark: ["#1C1C1E", "#111113"] },
  },
  {
    id: "sand",
    label: "Sand",
    group: "neutral",
    stops: { light: ["#F7F3EE", "#EBE3D8"], dark: ["#1F1C19", "#15130F"] },
  },
  {
    id: "slate",
    label: "Slate",
    group: "neutral",
    stops: { light: ["#EEF1F5", "#DCE2EA"], dark: ["#1A1D22", "#0F1215"] },
  },
  {
    id: "sky",
    label: "Sky",
    group: "gradient",
    stops: {
      light: ["#D6E8FF", "#DDF2F5", "#EFE6FF"],
      dark: ["#0B2547", "#0D3440", "#21173D"],
    },
  },
  {
    id: "dusk",
    label: "Dusk",
    group: "gradient",
    stops: {
      light: ["#EADCFF", "#FFDDEB", "#FFE7D6"],
      dark: ["#2A1748", "#3E1533", "#3A2014"],
    },
  },
  {
    id: "meadow",
    label: "Meadow",
    group: "gradient",
    stops: {
      light: ["#D9F2DF", "#DDF1EC", "#EEF5D6"],
      dark: ["#0F2E1C", "#0C2D2A", "#252C0E"],
    },
  },
  {
    id: "sunrise",
    label: "Sunrise",
    group: "gradient",
    stops: {
      light: ["#FFE4CC", "#FFDADA", "#FFF0C7"],
      dark: ["#3A1E0C", "#3A1216", "#33280A"],
    },
  },
  {
    id: "aurora",
    label: "Aurora",
    group: "gradient",
    stops: {
      light: ["#D8F5EC", "#DCE4FF", "#F5DCF2"],
      dark: ["#0B2E2A", "#16204A", "#331437"],
    },
  },
];

export const DEFAULT_BACKGROUND = "mist";

export function findBackground(id: string): Background {
  return backgrounds.find((b) => b.id === id) ?? backgrounds[0]!;
}

/** The CSS `background` for a preset: soft colour washes for gradients, a gentle fall for neutrals. */
export function backgroundCss(background: Background, mode: Mode): string {
  const s = background.stops[mode];
  if (s.length < 3) return `linear-gradient(180deg, ${s[0]} 0%, ${s[1]} 100%)`;
  return [
    `radial-gradient(120% 90% at 0% 0%, ${s[0]} 0%, transparent 62%)`,
    `radial-gradient(110% 90% at 100% 100%, ${s[2]} 0%, transparent 60%)`,
    `linear-gradient(135deg, ${s[0]} 0%, ${s[1]} 50%, ${s[2]} 100%)`,
  ].join(", ");
}

/** Write the palette as CSS variables on <html>, and tell HeroUI which mode is on. */
export function applyTheme(mode: Mode, root: HTMLElement = document.documentElement): void {
  const p = palettes[mode];
  const vars: Record<string, string> = {
    // HeroUI's variables
    "--foreground": p.foreground,
    "--surface-foreground": p.foreground,
    "--overlay-foreground": p.foreground,
    "--default-foreground": p.foreground,
    "--muted": p.muted,
    "--accent": p.accent,
    "--accent-foreground": p.accentForeground,
    "--success": p.success,
    "--warning": p.warning,
    "--danger": p.danger,
    "--focus": p.accentText,
    "--link": p.accentText,
    "--surface": p.glass,
    "--overlay": p.sheet,
    "--border": p.hairline,
    "--separator": p.hairline,
    "--field-background": p.field,
    "--default": p.field,
    // Tandem's own
    "--tandem-glass": p.glass,
    "--tandem-sheet": p.sheet,
    "--tandem-hairline": p.hairline,
    "--tandem-scrim": p.scrim,
    "--tandem-shadow": p.shadow,
    "--tandem-accent-text": p.accentText,
  };
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value);
  root.classList.toggle("dark", mode === "dark");
  root.classList.toggle("light", mode === "light");
  root.dataset.theme = mode;
  root.style.colorScheme = mode;
}

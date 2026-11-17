/**
 * Light or dark mode: the person's choice, or the system's. Kept in localStorage under "theme"
 * (the key the app has always used), and applied as the `dark` class on <html>.
 *
 * index.html applies the saved choice before the first paint, so the page never flashes the
 * wrong theme; this store keeps it applied afterwards and follows the system while the choice
 * is "system".
 */
import { create } from "zustand";

export type Theme = "light" | "dark" | "system";
type Resolved = "light" | "dark";

const KEY = "theme";
const media = window.matchMedia("(prefers-color-scheme: dark)");

function saved(): Theme {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

const resolve = (theme: Theme): Resolved =>
  theme === "system" ? (media.matches ? "dark" : "light") : theme;

/** Switch without every colour animating across the page at once. */
function apply(resolved: Resolved) {
  const root = document.documentElement;
  const pause = document.createElement("style");
  pause.textContent = "*,*::before,*::after{transition:none!important}";
  document.head.appendChild(pause);
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
  // Make the browser apply the new colours now, then let transitions back in. A timer, not an
  // animation frame, so a tab in the background doesn't keep transitions off.
  void window.getComputedStyle(document.body).opacity;
  setTimeout(() => pause.remove(), 1);
}

type ThemeState = {
  theme: Theme;
  resolvedTheme: Resolved;
  setTheme: (theme: Theme) => void;
};

export const useTheme = create<ThemeState>()((set) => ({
  theme: saved(),
  resolvedTheme: resolve(saved()),
  setTheme: (theme) => {
    try {
      localStorage.setItem(KEY, theme);
    } catch {
      // Private mode or blocked storage: the choice lasts for this page only.
    }
    const resolvedTheme = resolve(theme);
    apply(resolvedTheme);
    set({ theme, resolvedTheme });
  },
}));

media.addEventListener("change", () => {
  const { theme } = useTheme.getState();
  if (theme !== "system") return;
  const resolvedTheme = resolve(theme);
  apply(resolvedTheme);
  useTheme.setState({ resolvedTheme });
});

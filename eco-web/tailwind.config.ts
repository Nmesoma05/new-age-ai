import type { Config } from "tailwindcss";

// Colours come from the Ecosystem design system tokens (src/app/globals.css), so light/dark switch in one place.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        cream: v("cream"), raised: v("cream-raised"), sunken: v("cream-sunken"), line: v("line"),
        control: v("control-border"), ink: v("ink"), muted: v("ink-muted"), orange: v("orange"),
        "on-orange": v("on-orange"), "orange-text": v("orange-text"), "orange-soft": v("orange-soft"),
        sidebar: v("sidebar-bg"), "sidebar-ink": v("sidebar-ink"), "sidebar-muted": v("sidebar-muted"),
        "sidebar-hover": v("sidebar-hover"), d1: v("d1-creator"), "d1-soft": v("d1-soft"), d2: v("d2-business"), "d2-soft": v("d2-soft"), d3: v("d3-freelancer"), "d3-soft": v("d3-soft"), "on-division": v("on-division"),
        success: v("success"), "success-soft": v("success-soft"), warning: v("warning"), "warning-soft": v("warning-soft"),
        danger: v("danger"), "danger-soft": v("danger-soft"),
      },
      fontFamily: {
        display: ['"Bricolage Grotesque"', '"Instrument Sans"', "system-ui", "sans-serif"],
        sans: ['"Instrument Sans"', "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "Menlo", "monospace"],
      },
      borderRadius: { s: "6px", m: "10px", l: "18px" },
      boxShadow: {
        1: "0 1px 2px rgba(23,23,23,0.06), 0 4px 12px rgba(23,23,23,0.06)",
        2: "0 12px 40px rgba(23,23,23,0.18)",
      },
      keyframes: {
        rise: { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
      },
      animation: { rise: "rise 200ms ease-out both", shimmer: "shimmer 1.4s linear infinite" },
    },
  },
  plugins: [],
} satisfies Config;

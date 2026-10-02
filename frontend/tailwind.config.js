/** @type {import('tailwindcss').Config} */
// Every colour resolves to a CSS variable in src/tokens.css. Tailwind v3 cannot
// apply an opacity modifier (bg-brand/50) to a var() colour — it silently emits
// nothing; postbuild.mjs fails the build if one is used.
export default {
  content: ["./index.html", "./src/**/*.{vue,js}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "var(--kgs-brand)", deep: "var(--kgs-brand-deep)", soft: "var(--kgs-brand-soft)" },
        ink: { DEFAULT: "var(--kgs-ink)", muted: "var(--kgs-ink-muted)", faint: "var(--kgs-ink-faint)" },
        surface: { DEFAULT: "var(--kgs-surface)", page: "var(--kgs-page)", line: "var(--kgs-line)" },
        ok: { text: "var(--kgs-ok-text)", bg: "var(--kgs-ok-bg)" },
        warn: { text: "var(--kgs-warn-text)", bg: "var(--kgs-warn-bg)" },
        danger: { text: "var(--kgs-danger-text)", bg: "var(--kgs-danger-bg)" },
      },
      minHeight: { action: "56px", secondary: "48px" },
    },
  },
  plugins: [],
}

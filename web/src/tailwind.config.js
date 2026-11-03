/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        elevated: "var(--surface)",
        surface: "var(--surface)",
        tint: "var(--tint)",
        ink: "var(--text-1)",
        muted: "var(--text-2)",
        soft: "var(--text-3)",
        line: "var(--line)",
        "line-strong": "var(--line-strong)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        "accent-text": "var(--accent-text)",
        danger: "var(--danger)",
        ok: "var(--done-text)",
        done: "var(--done)",
        "done-bg": "var(--done-bg)",
      },
      borderRadius: {
        sm: "var(--r-sm)",
        md: "var(--r-md)",
        lg: "var(--r-lg)",
        xl: "var(--r-xl)",
        "2xl": "var(--r-xl)",
      },
      spacing: {
        page: "var(--page-x)",
      },
      fontSize: {
        display: ["var(--fs-display)", { lineHeight: "1.2", fontWeight: "600" }],
        title: ["var(--fs-title)", { lineHeight: "1.3" }],
        body: ["var(--fs-body)", { lineHeight: "1.55" }],
        meta: ["var(--fs-meta)", { lineHeight: "1.4" }],
        label: ["var(--fs-label)", { lineHeight: "1.3" }],
        micro: ["var(--fs-micro)", { lineHeight: "1.3" }],
      },
      fontFamily: {
        display: ["var(--font-sans)"],
        body: ["var(--font-sans)"],
        sans: ["var(--font-sans)"],
      },
      transitionDuration: {
        press: "120ms",
        state: "180ms",
        move: "300ms",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(.25, 1, .5, 1)",
      },
      boxShadow: {
        card: "var(--shadow-card)",
        float: "var(--shadow-float)",
      },
      zIndex: {
        sticky: "10",
        mask: "40",
        sheet: "50",
        dialog: "60",
        toast: "70",
      },
    },
  },
  plugins: [],
};

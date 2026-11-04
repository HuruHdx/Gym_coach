/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // 每个色必须是 rgb(var(--x-rgb) / <alpha-value>) 形式，
        // 否则 `bg-ink/40` 这类透明度工具类会被 Tailwind 静默丢弃（不报错、不生成 CSS）。
        // 对应的三元组变量在 gym-ui/tokens.css，改色值时两处要一起改。
        bg: "rgb(var(--bg-rgb) / <alpha-value>)",
        elevated: "rgb(var(--surface-rgb) / <alpha-value>)",
        surface: "rgb(var(--surface-rgb) / <alpha-value>)",
        tint: "rgb(var(--tint-rgb) / <alpha-value>)",
        ink: "rgb(var(--text-1-rgb) / <alpha-value>)",
        muted: "rgb(var(--text-2-rgb) / <alpha-value>)",
        soft: "rgb(var(--text-3-rgb) / <alpha-value>)",
        line: "rgb(var(--line-rgb) / <alpha-value>)",
        "line-strong": "rgb(var(--line-strong-rgb) / <alpha-value>)",
        accent: "rgb(var(--accent-rgb) / <alpha-value>)",
        "accent-ink": "rgb(var(--accent-ink-rgb) / <alpha-value>)",
        "accent-text": "rgb(var(--accent-text-rgb) / <alpha-value>)",
        danger: "rgb(var(--danger-rgb) / <alpha-value>)",
        ok: "rgb(var(--done-text-rgb) / <alpha-value>)",
        done: "rgb(var(--done-rgb) / <alpha-value>)",
        "done-bg": "rgb(var(--done-bg-rgb) / <alpha-value>)",
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

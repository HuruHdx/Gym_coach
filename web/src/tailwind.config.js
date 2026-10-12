/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        elevated: "var(--bg-elevated)",
        ink: "var(--ink)",
        muted: "var(--ink-muted)",
        line: "var(--line)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        danger: "var(--danger)",
        ok: "var(--ok)",
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "14px",
      },
      fontFamily: {
        display: [
          '"Manrope"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "system-ui",
          "sans-serif",
        ],
        body: [
          '"Source Sans 3"',
          '"PingFang SC"',
          '"Microsoft YaHei"',
          "system-ui",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};

/** @type {import('tailwindcss').Config} */
module.exports = {
  // Tema gelap diatur lewat atribut [data-theme="dark"] + CSS variable,
  // jadi tidak perlu varian `dark:` Tailwind.
  content: ["./web/templates/**/*.html", "./web/static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        card: "var(--card)",
        line: "var(--border)",
        "line-strong": "var(--border-strong)",
        ink: "var(--text)",
        muted: "var(--text-muted)",
        primary: {
          DEFAULT: "var(--primary)",
          strong: "var(--primary-strong)",
          on: "var(--on-primary)",
        },
        success: "var(--success)",
        danger: "var(--danger)",
        warning: "var(--warning)",
      },
      fontFamily: {
        sans: ['"Noto Sans"', "system-ui", "-apple-system", "sans-serif"],
        display: ['"Figtree"', '"Noto Sans"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      // Skala tipografi tetap: 13 / 15 / 17 / 20 / 26 / 32 px
      fontSize: {
        caption: ["13px", "1.45"],
        body: ["15px", "1.6"],
        lead: ["17px", "1.55"],
        h3: ["20px", "1.35"],
        h2: ["26px", "1.25"],
        h1: ["32px", "1.2"],
      },
      maxWidth: { content: "1120px" },
      borderRadius: { card: "10px", btn: "8px" },
      boxShadow: {
        card: "0 1px 2px rgb(15 23 42 / .06)",
        dialog: "0 8px 24px rgb(15 23 42 / .10)",
      },
    },
  },
  plugins: [],
};

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Brand — fixed values taken straight from the KOMPILO logo.
        brand: {
          DEFAULT: "#1B4DFF", // bleu vif — accent principal (barre du K, chevron clair)
          600: "#1540D6", // hover / accent plus foncé
          700: "#1E3A6E", // bleu intermédiaire (chevron sombre de l'emblème)
          navy: "#0A1628", // bleu nuit / encre
        },
        // Semantic tokens — driven by CSS variables so the theme flips
        // light (default, fond blanc) <-> dark via [data-theme="dark"].
        canvas: "rgb(var(--k-canvas) / <alpha-value>)", // fond de page
        surface: "rgb(var(--k-surface) / <alpha-value>)", // cartes / panneaux
        raised: "rgb(var(--k-raised) / <alpha-value>)", // champs / zones en relief
        line: "rgb(var(--k-line) / <alpha-value>)", // bordures
        ink: "rgb(var(--k-ink) / <alpha-value>)", // texte principal
        muted: "rgb(var(--k-muted) / <alpha-value>)", // texte secondaire
        subtle: "rgb(var(--k-subtle) / <alpha-value>)", // texte tertiaire
        accent: "rgb(var(--k-accent) / <alpha-value>)", // bleu vif (aplats)
        "accent-ink": "rgb(var(--k-accent-ink) / <alpha-value>)", // bleu en texte (contraste)
        ok: "rgb(var(--k-ok) / <alpha-value>)",
        warn: "rgb(var(--k-warn) / <alpha-value>)",
        danger: "rgb(var(--k-danger) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

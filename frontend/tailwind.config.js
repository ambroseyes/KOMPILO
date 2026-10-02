/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        kompilo: {
          navy: "#0A1628", // page background
          panel: "#0E1E38", // cards / panels
          raised: "#13294A", // inputs / raised surfaces
          border: "#1E3357",
          blue: "#1B4DFF", // primary accent
          "blue-600": "#1540D6",
          "blue-300": "#6C8BFF",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

import type { Config } from "tailwindcss";

export default {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        board: {
          light: "#ebecd0",
          dark: "#779556",
          highlight: "rgba(255, 255, 0, 0.4)",
          threat: "rgba(239, 68, 68, 0.4)",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;

import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#191970",
          hover: "#10104D",
        },
        background: "#f8fafc",
        foreground: "#333333",
        muted: "#6c757d",
        accent: {
          green: "#28a745",
          red: "#dc3545",
          blue: "#3b82f6",
          purple: "#764ba2",
          warning: "#ffc107",
        },
      },
      fontFamily: {
        sans: [
          "Inter",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      borderRadius: {
        card: "16px",
        button: "8px",
      },
      boxShadow: {
        subtle: "0 2px 10px rgba(0, 0, 0, 0.05)",
        card: "0 4px 20px rgba(0, 0, 0, 0.05)",
        hover: "0 8px 30px rgba(0, 0, 0, 0.1)",
      },
    },
  },
  plugins: [],
};
export default config;

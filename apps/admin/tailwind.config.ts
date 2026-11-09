import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172d2c",
        forest: "#1d5a50",
        sage: "#dce9df",
        sand: "#f6f3eb",
      },
      boxShadow: {
        card: "0 16px 42px rgba(23, 45, 44, 0.08)",
      },
    },
  },
  plugins: [],
};

export default config;

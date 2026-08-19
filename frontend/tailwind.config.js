/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // Placeholder theme — see assets/branding/gudsky/README.md.
        // Do NOT guess at brand colors; these are neutral defaults until
        // color-palette.md is supplied by Gudsky Research Foundation.
        brand: {
          primary: "#2E5B8A",
          accent: "#B5762B",
        },
      },
    },
  },
  plugins: [],
};

/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Real brand color, pulled directly from the Gudsky Research
        // Foundation seal logo (#1341b1 is the exact dominant blue).
        brand: {
          50: '#eaeffb',
          100: '#c7d4f3',
          500: '#1341b1',
          600: '#0f3596',
          700: '#0d2f86',
        },
      },
    },
  },
  plugins: [],
};

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Geist', 'sans-serif'],
        mono: ['Geist Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        card: '#1E201F',
        raised: '#2C2E2D',
        pick: '#383E3A',
        mute: '#9A9C9B',
        ink: '#F4F4F2',
        epl: '#E90052',
        pitch: '#00FF85',
        club: '#38003C',
      },
    },
  },
  plugins: [],
}

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        // Semantic research-UI surface tokens
        surface: {
          base: '#020817',   // slate-950
          subtle: '#0f172a', // slate-900
          card: '#1e293b',   // slate-800
          raised: '#273449', // slightly lighter
        },
        // Game-specific player/element colors
        player1: '#38bdf8', // sky-400
        player2: '#fbbf24', // amber-400
        // Energy type colors
        fire: '#F97316',
        water: '#3B82F6',
        grass: '#10B981',
        lightning: '#FBBF24',
        psychic: '#EC4899',
        fighting: '#D97706',
        dark: '#6B7280',
        metal: '#9CA3AF',
        dragon: '#8B5CF6',
        colorless: '#A1A1AA',
      },
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
      },
    },
  },
  plugins: [],
}

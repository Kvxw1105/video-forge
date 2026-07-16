/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        heading: ['"Cormorant Garamond"', '"Source Han Serif SC"', '"Noto Serif SC"', 'serif'],
        sans: ['"Crimson Pro"', '"Source Han Serif SC"', '"Noto Serif SC"', 'serif'],
        mono: ['"JetBrains Mono"', '"Cascadia Code"', 'Consolas', 'monospace'],
      },
      colors: {
        parchment: {
          50: '#f5f0e8',
          100: '#e8dfd2',
          200: '#d4c8b5',
          300: '#c8bfb0',
          400: '#a89e90',
          500: '#8b7e6f',
          600: '#6b5e4f',
          700: '#4a3f33',
          800: '#332e28',
          900: '#2a2520',
          950: '#1a1814',
        },
        gold: {
          DEFAULT: '#c49c60',
          light: '#e0c08a',
          dark: '#8b7355',
          muted: '#9a8060',
        },
        rust: {
          DEFAULT: '#a0674a',
          light: '#c4896a',
        },
        sage: {
          DEFAULT: '#7a8b6f',
          muted: '#6b7a62',
        },
      },
      boxShadow: {
        'cinematic': '0 4px 24px -4px rgba(0,0,0,0.4), 0 0 0 1px rgba(184,149,106,0.06)',
        'cinematic-lg': '0 8px 40px -8px rgba(0,0,0,0.5), 0 0 0 1px rgba(184,149,106,0.08)',
        'inner-glow': 'inset 0 1px 0 rgba(200,191,176,0.05)',
        'vignette': 'inset 0 0 60px rgba(0,0,0,0.3)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0', transform: 'translate(-50%, 8px)' },
          '100%': { opacity: '1', transform: 'translate(-50%, 0)' },
        },
        'grain': {
          '0%, 100%': { transform: 'translate(0, 0)' },
          '10%': { transform: 'translate(-5%, -10%)' },
          '30%': { transform: 'translate(3%, -15%)' },
          '50%': { transform: 'translate(12%, 9%)' },
          '70%': { transform: 'translate(9%, 4%)' },
          '90%': { transform: 'translate(-1%, 7%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.3s ease-out',
        'grain': 'grain 8s steps(10) infinite',
      },
    },
  },
  plugins: [],
}

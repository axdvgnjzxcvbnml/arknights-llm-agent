/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // 深色游戏感底色
        ink: {
          950: '#080b12',
          900: '#0c1119',
          850: '#111823',
          800: '#16202c',
          700: '#1e2a38',
          600: '#2a3a4d',
          500: '#3d5068',
        },
        // 证据分级配色（与 src/constants/evidence.js 一一对应）
        ev: {
          fact: '#34d399',
          annotated: '#2dd4bf',
          cv: '#22d3ee',
          retrieved: '#60a5fa',
          inferred: '#a78bfa',
          estimated: '#fbbf24',
          mock: '#94a3b8',
        },
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Microsoft YaHei"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-soft': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '.45' },
        },
      },
      animation: {
        'fade-up': 'fade-up .22s ease-out both',
        'pulse-soft': 'pulse-soft 1.6s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}

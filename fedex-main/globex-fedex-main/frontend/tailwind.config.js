/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          purple: '#6D28FF',
          'purple-dark': '#5b21e6',
          orange: '#FF6600',
        },
        login: {
          bg: '#F8FAFC',
          ink: '#0F172A',
          muted: '#64748B',
          border: '#E5E7EB',
        },
      },
      borderRadius: {
        '4xl': '32px',
      },
      boxShadow: {
        'login-card': '0 30px 80px rgba(109, 40, 255, 0.12)',
        'login-btn': '0 8px 24px rgba(109, 40, 255, 0.28)',
      },
      fontFamily: {
        sans: ['Inter', 'Plus Jakarta Sans', 'system-ui', 'sans-serif'],
      },
      transitionDuration: {
        DEFAULT: '250ms',
      },
    },
  },
  plugins: [],
};

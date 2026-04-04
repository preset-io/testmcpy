/** @type {import('tailwindcss').Config} */

// Helper to create color with alpha support from CSS variable containing RGB channels
const c = (varName) => `rgb(var(${varName}) / <alpha-value>)`

export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        background: {
          DEFAULT: c('--color-background'),
          subtle: c('--color-background-subtle'),
        },
        surface: {
          DEFAULT: c('--color-surface'),
          hover: c('--color-surface-hover'),
          elevated: c('--color-surface-elevated'),
        },
        border: {
          DEFAULT: c('--color-border'),
          subtle: c('--color-border-subtle'),
        },
        primary: {
          DEFAULT: c('--color-primary'),
          hover: c('--color-primary-hover'),
          light: c('--color-primary-light'),
          dark: c('--color-primary-dark'),
        },
        success: {
          DEFAULT: c('--color-success'),
          light: c('--color-success-light'),
          dark: c('--color-success-dark'),
        },
        error: {
          DEFAULT: c('--color-error'),
          light: c('--color-error-light'),
          dark: c('--color-error-dark'),
        },
        warning: {
          DEFAULT: c('--color-warning'),
          light: c('--color-warning-light'),
          dark: c('--color-warning-dark'),
        },
        info: {
          DEFAULT: c('--color-info'),
          light: c('--color-info-light'),
          dark: c('--color-info-dark'),
        },
        text: {
          primary: c('--color-text-primary'),
          secondary: c('--color-text-secondary'),
          tertiary: c('--color-text-tertiary'),
          disabled: c('--color-text-disabled'),
        },
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
      },
      boxShadow: {
        'soft': 'var(--shadow-soft)',
        'medium': 'var(--shadow-medium)',
        'strong': 'var(--shadow-strong)',
        'glow-primary': 'var(--shadow-glow-primary)',
        'glow-success': 'var(--shadow-glow-success)',
        'inner-soft': 'var(--shadow-inner-soft)',
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-in-out',
        'slide-in': 'slideIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-soft': 'pulseSoft 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'shimmer': 'shimmer 2s linear infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(20px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.5' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}

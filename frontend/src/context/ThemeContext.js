import { createContext, useContext } from 'react'

export const ThemeContext = createContext(null)

export const DEFAULT_THEME_FALLBACK = {
  theme: 'light',
  isDark: false,
  toggleTheme: () => {},
  setTheme: () => {},
}

export function useTheme() {
  const context = useContext(ThemeContext)
  if (!context) {
    return DEFAULT_THEME_FALLBACK
  }
  return context
}

export { ThemeProvider } from './ThemeContext.jsx'

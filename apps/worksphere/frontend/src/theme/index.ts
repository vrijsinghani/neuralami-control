/**
 * WorkSphere Theme Configuration
 */

import { createTheme, Theme } from '@mui/material/styles';

// Base styles
import colors from './base/colors';
import typography from './base/typography';
import breakpoints from './base/breakpoints';
import borders from './base/borders';
import boxShadows from './base/boxShadows';

// Helper functions
import { boxShadow } from './functions/boxShadow';
import { hexToRgb } from './functions/hexToRgb';
import { linearGradient } from './functions/linearGradient';
import { pxToRem } from './functions/pxToRem';
import { rgba } from './functions/rgba';

// Define theme augmentation for custom properties
declare module '@mui/material/styles' {
  interface Theme {
    borders: typeof borders;
    boxShadows: typeof boxShadows;
    functions: {
      boxShadow: typeof boxShadow;
      hexToRgb: typeof hexToRgb;
      linearGradient: typeof linearGradient;
      pxToRem: typeof pxToRem;
      rgba: typeof rgba;
    };
  }

  interface ThemeOptions {
    borders?: typeof borders;
    boxShadows?: typeof boxShadows;
    functions?: {
      boxShadow?: typeof boxShadow;
      hexToRgb?: typeof hexToRgb;
      linearGradient?: typeof linearGradient;
      pxToRem?: typeof pxToRem;
      rgba?: typeof rgba;
    };
  }

  interface SimplePaletteColorOptions {
    focus?: string;
  }

  interface PaletteColor {
    focus?: string;
  }

  interface TypeBackground {
    default: string;
    paper: string;
  }

  interface Palette {
    gradients: {
      primary: { main: string; state: string };
      secondary: { main: string; state: string };
      info: { main: string; state: string };
      success: { main: string; state: string };
      warning: { main: string; state: string };
      error: { main: string; state: string };
      light: { main: string; state: string };
      dark: { main: string; state: string };
    };
    badgeColors: {
      primary: { background: string; text: string };
      secondary: { background: string; text: string };
      info: { background: string; text: string };
      success: { background: string; text: string };
      warning: { background: string; text: string };
      error: { background: string; text: string };
      light: { background: string; text: string };
      dark: { background: string; text: string };
    };
    transparent: { main: string };
    white: { main: string; focus: string };
    dark: { main: string; focus: string };
    light: SimplePaletteColorOptions;
  }

  interface PaletteOptions {
    gradients?: {
      primary?: { main: string; state: string };
      secondary?: { main: string; state: string };
      info?: { main: string; state: string };
      success?: { main: string; state: string };
      warning?: { main: string; state: string };
      error?: { main: string; state: string };
      light?: { main: string; state: string };
      dark?: { main: string; state: string };
    };
    badgeColors?: {
      primary?: { background: string; text: string };
      secondary?: { background: string; text: string };
      info?: { background: string; text: string };
      success?: { background: string; text: string };
      warning?: { background: string; text: string };
      error?: { background: string; text: string };
      light?: { background: string; text: string };
      dark?: { background: string; text: string };
    };
    transparent?: { main: string };
    white?: { main: string; focus: string };
    dark?: { main: string; focus: string };
    light?: SimplePaletteColorOptions;
  }
}

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: colors.primary.main,
      focus: colors.primary.focus,
    },
    secondary: {
      main: colors.secondary.main,
      focus: colors.secondary.focus,
    },
    info: {
      main: colors.info.main,
      focus: colors.info.focus,
    },
    success: {
      main: colors.success.main,
      focus: colors.success.focus,
    },
    warning: {
      main: colors.warning.main,
      focus: colors.warning.focus,
    },
    error: {
      main: colors.error.main,
      focus: colors.error.focus,
    },
    light: {
      main: colors.light.main,
      focus: colors.light.focus,
    },
    dark: {
      main: colors.dark.main,
      focus: colors.dark.focus,
    },
    grey: {
      100: colors.grey[100],
      200: colors.grey[200],
      300: colors.grey[300],
      400: colors.grey[400],
      500: colors.grey[500],
      600: colors.grey[600],
      700: colors.grey[700],
      800: colors.grey[800],
      900: colors.grey[900],
    },
    gradients: {
      primary: colors.gradients.primary,
      secondary: colors.gradients.secondary,
      info: colors.gradients.info,
      success: colors.gradients.success,
      warning: colors.gradients.warning,
      error: colors.gradients.error,
      light: colors.gradients.light,
      dark: colors.gradients.dark,
    },
    badgeColors: colors.badgeColors,
    text: { 
      primary: colors.dark.main, 
      secondary: colors.grey[600] 
    },
    transparent: { main: 'transparent' },
    white: colors.white,
    background: { 
      default: colors.light.main,
      paper: colors.white.main,
    },
    divider: colors.grey[300],
  },
  typography: typography as any, // Temporary fix for typography type mismatch
  breakpoints,
  shape: {
    borderRadius: borders.borderRadius.md,
  },
  borders,
  boxShadows,
  functions: {
    boxShadow,
    hexToRgb,
    linearGradient,
    pxToRem,
    rgba,
  },
});

console.log('Theme gradients:', theme.palette.gradients);

export type WorkSphereTheme = Theme & {
  borders: typeof borders;
  boxShadows: typeof boxShadows;
  functions: {
    boxShadow: typeof boxShadow;
    hexToRgb: typeof hexToRgb;
    linearGradient: typeof linearGradient;
    pxToRem: typeof pxToRem;
    rgba: typeof rgba;
  };
};

export default theme;

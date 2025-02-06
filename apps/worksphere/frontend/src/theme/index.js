import { createTheme } from '@mui/material/styles';

// Base colors
const colors = {
  background: {
    default: '#f8f9fa',
    paper: '#ffffff',
  },
  primary: {
    main: '#cb0c9f',
    light: '#e293d3',
    lighter: '#fce7f6',
    dark: '#8e0870',
    contrastText: '#ffffff',
  },
  secondary: {
    main: '#8392ab',
    light: '#96a2b8',
    dark: '#5c6b81',
    contrastText: '#ffffff',
  },
  success: {
    main: '#82d616',
    light: '#95dc47',
    dark: '#5a9510',
    contrastText: '#ffffff',
  },
  error: {
    main: '#ea0606',
    light: '#ef4646',
    dark: '#a30404',
    contrastText: '#ffffff',
  },
  warning: {
    main: '#fbcf33',
    light: '#fcd76a',
    dark: '#af9023',
    contrastText: '#ffffff',
  },
  info: {
    main: '#17c1e8',
    light: '#3dd0ef',
    dark: '#0f87a2',
    contrastText: '#ffffff',
  },
  text: {
    primary: '#344767',
    secondary: '#67748e',
    disabled: '#94a3b8',
  },
};

// Typography
const typography = {
  fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  h1: {
    fontSize: '2.25rem',
    fontWeight: 700,
    lineHeight: 1.3,
  },
  h2: {
    fontSize: '1.875rem',
    fontWeight: 700,
    lineHeight: 1.3,
  },
  h3: {
    fontSize: '1.5rem',
    fontWeight: 700,
    lineHeight: 1.375,
  },
  h4: {
    fontSize: '1.125rem',
    fontWeight: 700,
    lineHeight: 1.375,
  },
  h5: {
    fontSize: '1rem',
    fontWeight: 700,
    lineHeight: 1.375,
  },
  h6: {
    fontSize: '0.875rem',
    fontWeight: 700,
    lineHeight: 1.625,
  },
  body1: {
    fontSize: '0.875rem',
    fontWeight: 400,
    lineHeight: 1.625,
  },
  body2: {
    fontSize: '0.75rem',
    fontWeight: 400,
    lineHeight: 1.6,
  },
  button: {
    fontSize: '0.875rem',
    fontWeight: 700,
    lineHeight: 1.625,
    textTransform: 'none',
  },
};

// Create theme
const theme = createTheme({
  palette: colors,
  typography,
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          borderRadius: '0.5rem',
          padding: '0.625rem 1.5rem',
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: '1rem',
          boxShadow: '0 20px 27px 0 rgba(0, 0, 0, 0.05)',
        },
      },
    },
  },
});

export default theme; 
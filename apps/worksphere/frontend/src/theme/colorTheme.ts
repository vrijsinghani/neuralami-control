/**
 * WorkSphere Color Theme Configuration
 * This file allows for easy customization of the color theme.
 * Colors can be overridden by creating a custom theme file.
 */

export interface ColorTheme {
  base: {
    darkblue: string;
    darkbronze: string;
    lightbronze: string;
    steelgrey: string;
    cream: string;
    green: string;
    red: string;
  };
  theme: {
    primary: string;
    secondary: string;
    info: string;
    success: string;
    warning: string;
    danger: string;
    light: string;
    dark: string;
    white: string;
  };
  gradients: {
    primary: {
      main: string;
      state: string;
    };
    secondary: {
      main: string;
      state: string;
    };
    info: {
      main: string;
      state: string;
    };
    success: {
      main: string;
      state: string;
    };
    warning: {
      main: string;
      state: string;
    };
    error: {
      main: string;
      state: string;
    };
    dark: {
      main: string;
      state: string;
    };
    light: {
      main: string;
      state: string;
    };
  };
  grays: {
    100: string;
    200: string;
    300: string;
    400: string;
    500: string;
    600: string;
    700: string;
    800: string;
    900: string;
    black: string;
  };
  extended: {
    blue: string;
    indigo: string;
    purple: string;
    pink: string;
    orange: string;
    yellow: string;
    teal: string;
    cyan: string;
  };
}

export const defaultColorTheme: ColorTheme = {
  base: {
    darkblue: '#1a2c4c',
    darkbronze: '#af7657',
    lightbronze: '#e1c08e',
    steelgrey: '#90a4ae',
    cream: '#f4edd5',
    green: '#1f7713',
    red: '#F56565',
  },
  theme: {
    primary: '#1a2c4c',    // darkblue
    secondary: '#90a4ae',  // steelgrey
    info: '#af7657',       // darkbronze
    success: '#1f7713',    // green
    warning: '#e1c08e',    // lightbronze
    danger: '#F56565',     // red
    light: '#90a4ae',      // steelgrey
    dark: '#1a2c4c',       // darkblue
    white: '#ffffff',
  },
  gradients: {
    primary: {
      main: '#af7657',     // info
      state: '#1a2c4c',    // primary
    },
    secondary: {
      main: '#AF7657',
      state: '#e1c08e',
    },
    info: {
      main: '#90A4AE',
      state: '#1a2c4c',
    },
    success: {
      main: '#1f7713',
      state: '#1a2c4c',
    },
    warning: {
      main: '#E1C08E',
      state: '#1a2c4c',
    },
    error: {
      main: '#C85A54',
      state: '#1a2c4c',
    },
    dark: {
      main: '#141727',     // darken(primary, 10%)
      state: '#1a2c4c',    // darken(primary, 5%)
    },
    light: {
      main: '#F4EDD5',
      state: '#FFF6E6',
    },
  },
  grays: {
    100: '#F4F6F7',
    200: '#E9ECF0',
    300: '#DDE2E7',
    400: '#CED4DA',
    500: '#A7B2BF',
    600: '#768396',
    700: '#495667',
    800: '#2D3848',
    900: '#1A2433',
    black: '#0A1219',
  },
  extended: {
    blue: '#3F5C84',
    indigo: '#4B567A',
    purple: '#6A5C7C',
    pink: '#AF7F89',
    orange: '#D89B76',
    yellow: '#E1C08E',
    teal: '#517A7E',
    cyan: '#5B8B9C',
  },
};

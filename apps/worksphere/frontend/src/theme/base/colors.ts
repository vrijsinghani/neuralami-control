import { defaultColorTheme, ColorTheme } from '../colorTheme';

// You can override the default theme by providing a custom theme
let activeTheme: ColorTheme = defaultColorTheme;

export const setTheme = (newTheme: Partial<ColorTheme>) => {
  activeTheme = { ...defaultColorTheme, ...newTheme };
};

const colors = {
  background: {
    default: activeTheme.grays[100],
  },

  text: {
    main: activeTheme.grays[700],
    focus: activeTheme.grays[700],
  },

  transparent: {
    main: "transparent",
  },

  white: {
    main: activeTheme.theme.white,
    focus: activeTheme.theme.white,
  },

  black: {
    light: activeTheme.grays[800],
    main: activeTheme.grays.black,
    focus: activeTheme.grays.black,
  },

  primary: {
    main: activeTheme.theme.primary,
    focus: activeTheme.grays[800],
  },

  secondary: {
    main: activeTheme.theme.secondary,
    focus: activeTheme.grays[600],
  },

  info: {
    main: activeTheme.theme.info,
    focus: activeTheme.base.darkbronze,
  },

  success: {
    main: activeTheme.theme.success,
    focus: activeTheme.base.green,
  },

  warning: {
    main: activeTheme.theme.warning,
    focus: activeTheme.base.lightbronze,
  },

  error: {
    main: activeTheme.theme.danger,
    focus: activeTheme.base.red,
  },

  light: {
    main: activeTheme.theme.light,
    focus: activeTheme.grays[400],
  },

  dark: {
    main: activeTheme.theme.dark,
    focus: activeTheme.base.darkblue,
  },

  grey: activeTheme.grays,

  gradients: activeTheme.gradients,

  socialMediaColors: {
    facebook: {
      main: "#3b5998",
      dark: "#344e86",
    },
    twitter: {
      main: "#55acee",
      dark: "#3ea1ec",
    },
    instagram: {
      main: "#125688",
      dark: "#0e456d",
    },
    linkedin: {
      main: "#0077b5",
      dark: "#00669c",
    },
    pinterest: {
      main: "#cc2127",
      dark: "#b21d22",
    },
    youtube: {
      main: "#e52d27",
      dark: "#c31f1a",
    },
    vimeo: {
      main: "#1ab7ea",
      dark: "#13a3d2",
    },
    slack: {
      main: "#3aaf85",
      dark: "#329874",
    },
    dribbble: {
      main: "#ea4c89",
      dark: "#e73177",
    },
    github: {
      main: "#24292e",
      dark: "#171a1d",
    },
    reddit: {
      main: "#ff4500",
      dark: "#e03d00",
    },
    tumblr: {
      main: "#35465c",
      dark: "#2a3749",
    },
  },

  badgeColors: {
    primary: {
      background: activeTheme.base.darkblue,
      text: activeTheme.theme.white,
    },
    secondary: {
      background: activeTheme.grays[600],
      text: activeTheme.theme.white,
    },
    info: {
      background: activeTheme.base.darkbronze,
      text: activeTheme.theme.white,
    },
    success: {
      background: activeTheme.base.green,
      text: activeTheme.theme.white,
    },
    warning: {
      background: activeTheme.base.lightbronze,
      text: activeTheme.grays[900],
    },
    error: {
      background: activeTheme.base.red,
      text: activeTheme.theme.white,
    },
    light: {
      background: activeTheme.grays[100],
      text: activeTheme.grays[900],
    },
    dark: {
      background: activeTheme.grays[900],
      text: activeTheme.theme.white,
    },
  },

  coloredShadows: {
    primary: "#e91e62",
    secondary: "#110e0e",
    info: "#00bbd4",
    success: "#4caf4f",
    warning: "#ff9900",
    error: "#f44336",
    light: "#adb5bd",
    dark: "#404040",
  },

  inputBorderColor: activeTheme.grays[400],

  tabs: {
    indicator: { boxShadow: activeTheme.base.darkblue },
  },
};

export default colors;

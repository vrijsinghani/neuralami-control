import colors from './colors';
import { pxToRem } from '../functions/pxToRem';

interface BaseProperties {
  fontFamily: string;
  fontWeightLight: number;
  fontWeightRegular: number;
  fontWeightMedium: number;
  fontWeightBold: number;
  fontSizeXXS: string;
  fontSizeXS: string;
  fontSizeSM: string;
  fontSizeMD: string;
  fontSizeLG: string;
  fontSizeXL: string;
}

interface HeadingProperties {
  fontFamily: string;
  color: string;
  fontWeight: number;
}

interface DisplayProperties {
  fontFamily: string;
  color: string;
  fontWeight: number;
  lineHeight: number;
  fontSize: string;
}

export interface Typography {
  fontFamily: string;
  fontWeightLight: number;
  fontWeightRegular: number;
  fontWeightMedium: number;
  fontWeightBold: number;
  
  h1: HeadingProperties & { fontSize: string; lineHeight: number; };
  h2: HeadingProperties & { fontSize: string; lineHeight: number; };
  h3: HeadingProperties & { fontSize: string; lineHeight: number; };
  h4: HeadingProperties & { fontSize: string; lineHeight: number; };
  h5: HeadingProperties & { fontSize: string; lineHeight: number; };
  h6: HeadingProperties & { fontSize: string; lineHeight: number; };
  
  subtitle1: { fontSize: string; fontWeight: number; lineHeight: number; };
  subtitle2: { fontSize: string; fontWeight: number; lineHeight: number; };
  
  body1: { fontSize: string; fontWeight: number; lineHeight: number; };
  body2: { fontSize: string; fontWeight: number; lineHeight: number; };
  
  button: { fontSize: string; fontWeight: number; lineHeight: number; };
  caption: { fontSize: string; fontWeight: number; lineHeight: number; };
  overline: { fontSize: string; fontWeight: number; lineHeight: number; };
  
  d1: DisplayProperties;
  d2: DisplayProperties;
  d3: DisplayProperties;
  d4: DisplayProperties;
  d5: DisplayProperties;
  d6: DisplayProperties;
  
  size: {
    xxs: string;
    xs: string;
    sm: string;
    md: string;
    lg: string;
    xl: string;
  };
}

const baseProperties: BaseProperties = {
  fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
  fontWeightLight: 300,
  fontWeightRegular: 400,
  fontWeightMedium: 500,
  fontWeightBold: 700,
  fontSizeXXS: pxToRem(10.4),
  fontSizeXS: pxToRem(12),
  fontSizeSM: pxToRem(14),
  fontSizeMD: pxToRem(16),
  fontSizeLG: pxToRem(18),
  fontSizeXL: pxToRem(20),
};

const baseHeadingProperties: HeadingProperties = {
  fontFamily: baseProperties.fontFamily,
  color: colors.dark.main,
  fontWeight: baseProperties.fontWeightMedium,
};

const baseDisplayProperties: DisplayProperties = {
  fontFamily: baseProperties.fontFamily,
  color: colors.dark.main,
  fontWeight: baseProperties.fontWeightLight,
  lineHeight: 1.2,
  fontSize: pxToRem(45),
};

const typography: Typography = {
  fontFamily: baseProperties.fontFamily,
  fontWeightLight: baseProperties.fontWeightLight,
  fontWeightRegular: baseProperties.fontWeightRegular,
  fontWeightMedium: baseProperties.fontWeightMedium,
  fontWeightBold: baseProperties.fontWeightBold,

  h1: {
    ...baseHeadingProperties,
    fontSize: pxToRem(48),
    lineHeight: 1.25,
  },

  h2: {
    ...baseHeadingProperties,
    fontSize: pxToRem(36),
    lineHeight: 1.3,
  },

  h3: {
    ...baseHeadingProperties,
    fontSize: pxToRem(30),
    lineHeight: 1.375,
  },

  h4: {
    ...baseHeadingProperties,
    fontSize: pxToRem(24),
    lineHeight: 1.375,
  },

  h5: {
    ...baseHeadingProperties,
    fontSize: pxToRem(20),
    lineHeight: 1.375,
  },

  h6: {
    ...baseHeadingProperties,
    fontSize: pxToRem(16),
    lineHeight: 1.625,
  },

  subtitle1: {
    fontFamily: baseProperties.fontFamily,
    fontSize: baseProperties.fontSizeMD,
    fontWeight: baseProperties.fontWeightLight,
    lineHeight: 1.625,
  },

  subtitle2: {
    fontFamily: baseProperties.fontFamily,
    fontSize: baseProperties.fontSizeSM,
    fontWeight: baseProperties.fontWeightLight,
    lineHeight: 1.6,
  },

  body1: {
    fontFamily: baseProperties.fontFamily,
    fontSize: baseProperties.fontSizeMD,
    fontWeight: baseProperties.fontWeightRegular,
    lineHeight: 1.625,
  },

  body2: {
    fontFamily: baseProperties.fontFamily,
    fontSize: baseProperties.fontSizeSM,
    fontWeight: baseProperties.fontWeightLight,
    lineHeight: 1.6,
  },

  button: {
    fontFamily: baseProperties.fontFamily,
    fontSize: baseProperties.fontSizeSM,
    fontWeight: baseProperties.fontWeightLight,
    lineHeight: 1.5,
  },

  caption: {
    fontFamily: baseProperties.fontFamily,
    fontSize: baseProperties.fontSizeXS,
    fontWeight: baseProperties.fontWeightLight,
    lineHeight: 1.25,
  },

  overline: {
    fontFamily: baseProperties.fontFamily,
    fontSize: baseProperties.fontSizeXS,
    fontWeight: baseProperties.fontWeightRegular,
    lineHeight: 1.25,
  },

  d1: {
    ...baseDisplayProperties,
    fontSize: pxToRem(80),
  },

  d2: {
    ...baseDisplayProperties,
    fontSize: pxToRem(72),
  },

  d3: {
    ...baseDisplayProperties,
    fontSize: pxToRem(64),
  },

  d4: {
    ...baseDisplayProperties,
    fontSize: pxToRem(56),
  },

  d5: {
    ...baseDisplayProperties,
    fontSize: pxToRem(48),
  },

  d6: {
    ...baseDisplayProperties,
    fontSize: pxToRem(40),
  },

  size: {
    xxs: baseProperties.fontSizeXXS,
    xs: baseProperties.fontSizeXS,
    sm: baseProperties.fontSizeSM,
    md: baseProperties.fontSizeMD,
    lg: baseProperties.fontSizeLG,
    xl: baseProperties.fontSizeXL,
  },
};

export default typography;

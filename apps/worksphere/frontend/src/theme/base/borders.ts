/**
 * The base border styles for the WorkSphere theme.
 * Includes border width, radius, and color configurations.
 */

import colors from './colors';

export interface BorderBase {
  borderColor: string;
  borderWidth: {
    [key: number]: number;
  };
  borderRadius: {
    [key: string]: number;
  };
}

const borders: BorderBase = {
  borderColor: colors.grey[300],

  borderWidth: {
    0: 0,
    1: 1,
    2: 2,
    3: 3,
    4: 4,
    5: 5,
  },

  borderRadius: {
    xs: 2,
    sm: 4,
    md: 8,
    lg: 12,
    xl: 16,
    xxl: 24,
    section: 48,
    
    // Special values
    none: 0,
    xs2: 2.4,
    sm2: 4,
    md2: 8,
    lg2: 12,
    xl2: 16,
    xxl2: 24,
    
    // Pill and circle shapes
    pill: 9999,
    circle: 9999,
  },
};

export default borders;

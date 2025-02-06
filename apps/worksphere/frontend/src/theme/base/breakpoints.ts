/**
 * The base breakpoint values for the WorkSphere theme.
 * Following Material-UI's breakpoint system with TypeScript support.
 */

// Types from @mui/material
export interface Breakpoints {
  values: {
    xs: number;
    sm: number;
    md: number;
    lg: number;
    xl: number;
    xxl?: number;
  };
  unit: string;
  step: number;
}

const breakpoints: Breakpoints = {
  values: {
    xs: 0,      // Mobile first
    sm: 576,    // Small devices (landscape phones)
    md: 768,    // Medium devices (tablets)
    lg: 992,    // Large devices (desktops)
    xl: 1200,   // Extra large devices
    xxl: 1400,  // Extra extra large devices
  },
  unit: "px",
  step: 5,
};

export default breakpoints;

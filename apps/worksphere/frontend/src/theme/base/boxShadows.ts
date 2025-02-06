/**
 * The base box shadow styles for the WorkSphere theme.
 * Provides a consistent elevation system.
 */

import colors from './colors';
import { boxShadow } from '../functions/boxShadow';
import { rgba } from '../functions/rgba';

export interface BoxShadows {
  xs: string;
  sm: string;
  md: string;
  lg: string;
  xl: string;
  xxl: string;
  inset: string;
  colored: {
    primary: string;
    secondary: string;
    info: string;
    success: string;
    warning: string;
    error: string;
    light: string;
    dark: string;
  };
  navbarBoxShadow: string;
  sliderBoxShadow: {
    thumb: string;
  };
  tabsBoxShadow: {
    indicator: string;
  };
}

const boxShadows: BoxShadows = {
  xs: boxShadow([0, 2], [9, -5], rgba(colors.dark.main, 0.15), 0),
  sm: boxShadow([0, 5], [10, 0], rgba(colors.dark.main, 0.12), 0),
  md: `${boxShadow([0, 4], [6, -1], rgba(colors.dark.main, 0.10), 0)}, ${boxShadow(
    [0, 2],
    [4, -1],
    rgba(colors.dark.main, 0.06),
    0
  )}`,
  lg: `${boxShadow([0, 8], [26, -4], rgba(colors.dark.main, 0.15), 0)}, ${boxShadow(
    [0, 8],
    [9, -5],
    rgba(colors.dark.main, 0.06),
    0
  )}`,
  xl: `${boxShadow([0, 23], [45, -11], rgba(colors.dark.main, 0.25), 0)}, ${boxShadow(
    [0, 8],
    [15, -8],
    rgba(colors.dark.main, 0.08),
    0
  )}`,
  xxl: boxShadow([0, 20], [27, 0], rgba(colors.dark.main, 0.05), 0),
  inset: boxShadow([0, 1], [2, 0], rgba(colors.dark.main, 0.075), 0, "inset"),

  // Colored shadows
  colored: {
    primary: `${boxShadow([0, 4], [20, 0], colors.primary.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.primary.main, 0.4),
      0
    )}`,
    secondary: `${boxShadow([0, 4], [20, 0], colors.secondary.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.secondary.main, 0.4),
      0
    )}`,
    info: `${boxShadow([0, 4], [20, 0], colors.info.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.info.main, 0.4),
      0
    )}`,
    success: `${boxShadow([0, 4], [20, 0], colors.success.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.success.main, 0.4),
      0
    )}`,
    warning: `${boxShadow([0, 4], [20, 0], colors.warning.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.warning.main, 0.4),
      0
    )}`,
    error: `${boxShadow([0, 4], [20, 0], colors.error.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.error.main, 0.4),
      0
    )}`,
    light: `${boxShadow([0, 4], [20, 0], colors.light.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.light.main, 0.4),
      0
    )}`,
    dark: `${boxShadow([0, 4], [20, 0], colors.dark.main, 0.14)}, ${boxShadow(
      [0, 7],
      [10, -5],
      rgba(colors.dark.main, 0.4),
      0
    )}`,
  },

  // Component-specific shadows
  navbarBoxShadow: boxShadow([0, 0], [1, 1], colors.white.main, 0.9, "inset"),
  sliderBoxShadow: {
    thumb: boxShadow([0, 1], [13, 0], colors.dark.main, 0.2),
  },
  tabsBoxShadow: {
    indicator: boxShadow([0, 1], [5, 1], colors.tabs.indicator.boxShadow, 1),
  },
};

export default boxShadows;

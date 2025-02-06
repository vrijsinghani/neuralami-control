import { forwardRef, ReactNode } from 'react';
import { Typography, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';

// Types
type Color = 'inherit' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark' | 'text' | 'white' | 'black' | string;
type FontWeight = 'light' | 'regular' | 'medium' | 'bold' | false;
type TextTransform = 'none' | 'capitalize' | 'uppercase' | 'lowercase';
type VerticalAlign = 'unset' | 'baseline' | 'sub' | 'super' | 'text-top' | 'text-bottom' | 'middle' | 'top' | 'bottom';

interface SoftTypographyProps {
  color?: Color;
  fontWeight?: FontWeight;
  textTransform?: TextTransform;
  verticalAlign?: VerticalAlign;
  textGradient?: boolean;
  opacity?: number;
  children?: ReactNode;
  [key: string]: any; // for other Typography props
}

interface OwnerState {
  color: Color;
  textTransform: TextTransform;
  verticalAlign: VerticalAlign;
  fontWeight: FontWeight;
  opacity: number;
  textGradient: boolean;
}

const SoftTypographyRoot = styled(Typography, {
  shouldForwardProp: (prop) =>
    !['textTransform', 'fontWeight', 'verticalAlign', 'textGradient'].includes(String(prop)),
})<{ ownerState: OwnerState }>(({ theme, ownerState }) => {
  const { palette, typography, functions } = theme as WorkSphereTheme;
  const { color, textTransform, verticalAlign, fontWeight, opacity, textGradient } = ownerState;

  const { gradients, transparent } = palette;
  const { fontWeightLight, fontWeightRegular, fontWeightMedium, fontWeightBold } = typography;
  const { linearGradient } = functions;

  // fontWeight styles
  const fontWeights = {
    light: fontWeightLight,
    regular: fontWeightRegular,
    medium: fontWeightMedium,
    bold: fontWeightBold,
  };

  // styles for the typography with textGradient={true}
  const gradientStyles = () => ({
    backgroundImage:
      color !== 'inherit' && color !== 'text' && color !== 'white' && gradients[color as keyof typeof gradients]
        ? linearGradient(
            '180deg',
            gradients[color as keyof typeof gradients].main,
            gradients[color as keyof typeof gradients].state
          )
        : linearGradient(
            '180deg',
            gradients.dark.main,
            gradients.dark.state
          ),
    display: 'inline-block',
    WebkitBackgroundClip: 'text',
    WebkitTextFillColor: transparent.main,
    position: 'relative',
    zIndex: 1,
  });

  // Return the styles based on the props
  return {
    opacity,
    textTransform,
    verticalAlign,
    fontWeight: fontWeight && fontWeights[fontWeight],
    color:
      color === 'inherit' || !palette[color as keyof typeof palette]
        ? color
        : palette[color as keyof typeof palette]?.main || color,
    ...(textGradient && gradientStyles()),
  };
});

const SoftTypography = forwardRef<HTMLSpanElement, SoftTypographyProps>(
  (
    {
      color = 'dark',
      fontWeight = false,
      textTransform = 'none',
      verticalAlign = 'unset',
      textGradient = false,
      opacity = 1,
      children,
      ...rest
    },
    ref
  ) => (
    <SoftTypographyRoot
      {...rest}
      ref={ref}
      ownerState={{ color, textTransform, verticalAlign, fontWeight, opacity, textGradient }}
    >
      {children}
    </SoftTypographyRoot>
  )
);

SoftTypography.displayName = 'SoftTypography';

export default SoftTypography;

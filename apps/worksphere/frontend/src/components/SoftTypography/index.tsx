import { FC, forwardRef } from 'react';
import { Typography, TypographyProps, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';

// Types
type Color = 'inherit' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark' | 'text' | 'white' | 'black' | string;
type FontWeight = 'light' | 'regular' | 'medium' | 'bold' | false;
type TextTransform = 'none' | 'capitalize' | 'uppercase' | 'lowercase';
type VerticalAlign = 'unset' | 'baseline' | 'sub' | 'super' | 'text-top' | 'text-bottom' | 'middle' | 'top' | 'bottom';

interface SoftTypographyProps extends TypographyProps {
  color?: Color;
  fontWeight?: FontWeight;
  textTransform?: TextTransform;
  verticalAlign?: VerticalAlign;
  textGradient?: boolean;
  opacity?: number;
}

interface OwnerState {
  color: Color;
  textTransform: TextTransform;
  verticalAlign: VerticalAlign;
  fontWeight: FontWeight;
  opacity: number;
  textGradient: boolean;
}

const SoftTypographyRoot = styled(Typography)(({ theme, ownerState }: any) => {
  const { palette, typography, functions } = theme as WorkSphereTheme;
  const { color, textTransform, verticalAlign, fontWeight, opacity, textGradient } = ownerState;

  const { gradients, transparent, white } = palette;
  const { fontWeightLight, fontWeightRegular, fontWeightMedium, fontWeightBold } = typography;
  const { linearGradient } = functions;

  // fontWeight styles
  const fontWeights: { [key: string]: number } = {
    light: fontWeightLight,
    regular: fontWeightRegular,
    medium: fontWeightMedium,
    bold: fontWeightBold,
  };

  // color value
  let colorValue = color === "inherit" || !color ? "inherit" : palette[color]?.main || color;

  if (color === "text") {
    colorValue = palette.text?.main;
  } else if (color === "white") {
    colorValue = white.main;
  }

  return {
    opacity,
    textTransform,
    verticalAlign,
    textDecoration: "none",
    color: colorValue,
    fontWeight: fontWeights[fontWeight || "regular"] || fontWeightRegular,
    ...(textGradient && {
      backgroundImage:
        color !== "inherit" && color !== "text" && color !== "white" && gradients[color]
          ? linearGradient(gradients[color].main, gradients[color].state)
          : linearGradient(gradients.dark.main, gradients.dark.state),
      display: "inline-block",
      WebkitBackgroundClip: "text",
      WebkitTextFillColor: transparent.main,
      position: "relative",
      zIndex: 1,
    }),
  };
});

const SoftTypography: FC<SoftTypographyProps> = forwardRef(
  ({ color, fontWeight, textTransform, verticalAlign, textGradient, opacity, children, ...rest }, ref) => (
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

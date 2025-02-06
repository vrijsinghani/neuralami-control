import { forwardRef } from 'react';
import { Box, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';

// Types
type Variant = 'contained' | 'gradient';
type Color = 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'dark' | 'light' | 'white' | string;
type BorderRadius = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl' | 'section';
type Shadow = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl' | 'inset';

interface SoftBoxProps {
  variant?: Variant;
  bgColor?: Color;
  color?: Color;
  opacity?: number;
  borderRadius?: BorderRadius;
  shadow?: Shadow;
  [key: string]: any; // for other props that might be passed to Box
}

interface OwnerState {
  variant: Variant;
  bgColor: Color;
  color: Color;
  opacity: number;
  borderRadius: BorderRadius;
  shadow: Shadow;
}

const SoftBoxRoot = styled(Box, {
  shouldForwardProp: (prop) => 
    !['variant', 'bgColor', 'color', 'opacity', 'borderRadius', 'shadow'].includes(String(prop)),
})<{ ownerState: OwnerState }>(({ theme, ownerState }) => {
  const { palette, functions, borders, boxShadows } = theme as WorkSphereTheme;
  const { variant, bgColor, color, opacity, borderRadius, shadow } = ownerState;

  const { gradients, grey, white } = palette;
  const { linearGradient } = functions;
  const { borderRadius: radius } = borders;

  const greyColors = {
    'grey-100': grey[100],
    'grey-200': grey[200],
    'grey-300': grey[300],
    'grey-400': grey[400],
    'grey-500': grey[500],
    'grey-600': grey[600],
    'grey-700': grey[700],
    'grey-800': grey[800],
    'grey-900': grey[900],
  };

  const validGradients = [
    'primary',
    'secondary',
    'info',
    'success',
    'warning',
    'error',
    'dark',
    'light',
  ];

  const validColors = [
    'transparent',
    'white',
    'black',
    'primary',
    'secondary',
    'info',
    'success',
    'warning',
    'error',
    'light',
    'dark',
    ...Object.keys(greyColors),
  ];

  // Background value
  let backgroundValue = bgColor;

  if (variant === 'gradient') {
    backgroundValue = validGradients.find((el) => el === bgColor)
      ? linearGradient(
          gradients[bgColor as keyof typeof gradients].main,
          gradients[bgColor as keyof typeof gradients].state,
          '180deg'
        )
      : white.main;
  } else if (validColors.find((el) => el === bgColor)) {
    if (bgColor === 'transparent') {
      backgroundValue = 'transparent';
    } else if (bgColor.includes('grey')) {
      backgroundValue = greyColors[bgColor as keyof typeof greyColors];
    } else {
      backgroundValue = palette[bgColor as keyof typeof palette]?.main || white.main;
    }
  }

  // Color value
  let colorValue = color;

  if (validColors.find((el) => el === color)) {
    if (color === 'transparent') {
      colorValue = 'transparent';
    } else if (color.includes('grey')) {
      colorValue = greyColors[color as keyof typeof greyColors];
    } else {
      colorValue = palette[color as keyof typeof palette]?.main || white.main;
    }
  }

  return {
    opacity,
    background: backgroundValue,
    color: colorValue,
    borderRadius: radius[borderRadius],
    boxShadow: boxShadows[shadow],
  };
});

const SoftBox = forwardRef<HTMLDivElement, SoftBoxProps>(
  ({ variant = 'contained', bgColor = 'transparent', color = 'dark', opacity = 1, borderRadius = 'none', shadow = 'none', ...rest }, ref) => (
    <SoftBoxRoot
      {...rest}
      ref={ref}
      ownerState={{ variant, bgColor, color, opacity, borderRadius, shadow }}
    />
  )
);

SoftBox.displayName = 'SoftBox';

export default SoftBox;

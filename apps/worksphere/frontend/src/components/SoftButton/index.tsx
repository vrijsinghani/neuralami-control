import { forwardRef, ReactNode } from 'react';
import { Button, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';

// Types
type Color = 'white' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';
type Size = 'small' | 'medium' | 'large';
type Variant = 'text' | 'contained' | 'outlined' | 'gradient';

interface SoftButtonProps {
  color?: Color;
  variant?: Variant;
  size?: Size;
  circular?: boolean;
  iconOnly?: boolean;
  children?: ReactNode;
  [key: string]: any; // for other Button props
}

interface OwnerState {
  color: Color;
  variant: Variant;
  size: Size;
  circular: boolean;
  iconOnly: boolean;
}

const SoftButtonRoot = styled(Button, {
  shouldForwardProp: (prop) => !['color', 'variant', 'size', 'circular', 'iconOnly'].includes(String(prop)),
})<{ ownerState: OwnerState }>(({ theme, ownerState }) => {
  const { palette, functions, borders } = theme as WorkSphereTheme;
  const { color, variant, size, circular, iconOnly } = ownerState;

  const { white, dark, text, transparent, gradients } = palette;
  const { boxShadow, linearGradient, pxToRem, rgba } = functions;
  const { borderRadius } = borders;

  // styles for the button with variant="contained"
  const containedStyles = () => {
    // background color value
    const backgroundValue = palette[color]?.main || white.main;

    // backgroundColor value when button is focused
    const focusedBackgroundValue = palette[color]?.focus || white.focus;

    // boxShadow value
    const boxShadowValue = palette[color]
      ? boxShadow([0, 0], [0, 3.2], palette[color].main, 0.5)
      : boxShadow([0, 0], [0, 3.2], dark.main, 0.5);

    // color value
    let colorValue = white.main;

    if (color === 'white' || !palette[color]) {
      colorValue = text.main;
    } else if (color === 'light') {
      colorValue = gradients.dark.state;
    }

    // color value when button is focused
    let focusedColorValue = white.main;

    if (color === 'white') {
      focusedColorValue = text.main;
    } else if (color === 'primary' || color === 'error' || color === 'dark') {
      focusedColorValue = white.main;
    }

    return {
      background: backgroundValue,
      color: colorValue,
      boxShadow: boxShadowValue,

      '&:hover': {
        backgroundColor: focusedBackgroundValue,
        boxShadow: 'none',
      },

      '&:focus:not(:hover)': {
        backgroundColor: focusedBackgroundValue,
        boxShadow: boxShadowValue,
      },

      '&:disabled': {
        backgroundColor: backgroundValue,
        color: focusedColorValue,
      },
    };
  };

  // styles for the button with variant="outlined"
  const outliedStyles = () => {
    // background color value
    const backgroundValue = color === 'white' ? rgba(white.main, 0.1) : transparent.main;

    // color value
    const colorValue = palette[color]?.main || white.main;

    // boxShadow value
    const boxShadowValue = palette[color]
      ? boxShadow([0, 0], [0, 3.2], palette[color].main, 0.5)
      : boxShadow([0, 0], [0, 3.2], white.main, 0.5);

    // border color value
    let borderColorValue = palette[color]?.main || rgba(white.main, 0.75);

    if (color === 'white') {
      borderColorValue = rgba(white.main, 0.75);
    }

    return {
      background: backgroundValue,
      color: colorValue,
      borderColor: borderColorValue,

      '&:hover': {
        background: transparent.main,
        borderColor: colorValue,
        color: colorValue,
      },

      '&:focus:not(:hover)': {
        background: transparent.main,
        boxShadow: boxShadowValue,
        color: colorValue,
      },

      '&:active:not(:hover)': {
        backgroundColor: colorValue,
        color: white.main,
        opacity: 0.85,
      },

      '&:disabled': {
        color: colorValue,
        borderColor: colorValue,
      },
    };
  };

  // styles for the button with variant="gradient"
  const gradientStyles = () => {
    // Get gradient values from theme
    const gradientMain = gradients[color]?.main || white.main;
    const gradientState = gradients[color]?.state || white.main;

    return {
      background: linearGradient(
        'to right',
        gradientMain,
        gradientState
      ),
      color: white.main,

      '&:hover': {
        background: linearGradient(
          'to right',
          gradientMain,
          gradientState
        ),
        opacity: 0.9,
      },

      '&:focus:not(:hover)': {
        boxShadow: boxShadow([0, 0], [0, 3.2], gradientMain, 0.5),
      },

      '&:disabled': {
        background: linearGradient('to right', gradientMain, gradientState),
        opacity: 0.6,
      },
    };
  };

  // styles for the button with variant="text"
  const textStyles = () => {
    // color value
    const colorValue = palette[color]?.main || white.main;
    const focusedColorValue = palette[color]?.focus || white.focus;

    return {
      color: colorValue,

      '&:hover': {
        color: focusedColorValue,
      },

      '&:focus:not(:hover)': {
        color: focusedColorValue,
      },
    };
  };

  // styles for the button with circular={true}
  const circularStyles = () => ({
    borderRadius: borderRadius.section,
  });

  // styles for the button with iconOnly={true}
  const iconOnlyStyles = () => {
    // width, height, minWidth and minHeight values
    let sizeValue = pxToRem(38);

    if (size === 'small') {
      sizeValue = pxToRem(25.4);
    } else if (size === 'large') {
      sizeValue = pxToRem(52);
    }

    // padding value
    let paddingValue = `${pxToRem(11)} ${pxToRem(11)} ${pxToRem(10)}`;

    if (size === 'small') {
      paddingValue = pxToRem(4.5);
    } else if (size === 'large') {
      paddingValue = pxToRem(16);
    }

    return {
      width: sizeValue,
      minWidth: sizeValue,
      height: sizeValue,
      minHeight: sizeValue,
      padding: paddingValue,

      '& .material-icons': {
        marginTop: 0,
      },

      '&:hover, &:focus, &:active': {
        transform: 'none',
      },
    };
  };

  return {
    ...(variant === 'contained' && containedStyles()),
    ...(variant === 'outlined' && outliedStyles()),
    ...(variant === 'gradient' && gradientStyles()),
    ...(variant === 'text' && textStyles()),
    ...(circular && circularStyles()),
    ...(iconOnly && iconOnlyStyles()),
  };
});

const SoftButton = forwardRef<HTMLButtonElement, SoftButtonProps>(
  ({ color = 'info', variant = 'contained', size = 'medium', circular = false, iconOnly = false, children, ...rest }, ref) => {
    const ownerState = {
      color,
      variant,
      size,
      circular,
      iconOnly,
    };

    return (
      <SoftButtonRoot
        {...rest}
        ref={ref}
        variant={variant === 'gradient' ? 'contained' : variant}
        ownerState={ownerState}
      >
        {children}
      </SoftButtonRoot>
    );
  }
);

SoftButton.displayName = 'SoftButton';

export default SoftButton;

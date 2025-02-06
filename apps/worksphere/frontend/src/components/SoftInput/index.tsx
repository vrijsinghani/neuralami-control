import { forwardRef, ReactNode } from 'react';
import { InputBase, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';

// Types
type Size = 'small' | 'medium' | 'large';
type IconDirection = 'left' | 'right';
type Direction = 'ltr' | 'rtl';

interface Icon {
  component: ReactNode;
  direction: IconDirection;
}

interface SoftInputProps {
  size?: Size;
  icon?: Icon;
  error?: boolean;
  success?: boolean;
  disabled?: boolean;
  [key: string]: any; // for other InputBase props
}

interface InputOwnerState {
  size: Size;
  error: boolean;
  success: boolean;
  iconDirection?: IconDirection;
  direction: Direction;
  disabled: boolean;
}

interface IconOwnerState {
  size: Size;
}

// Styled components
const SoftInputRoot = styled(InputBase, {
  shouldForwardProp: (prop) => 
    !['size', 'error', 'success', 'iconDirection', 'direction', 'disabled'].includes(String(prop)),
})<{ ownerState: InputOwnerState }>(({ theme, ownerState }) => {
  const { palette, boxShadows, functions, typography, borders } = theme as WorkSphereTheme;
  const { size, error, success, iconDirection, direction, disabled } = ownerState;

  const { inputColors, grey, white, transparent } = palette;
  const { inputBoxShadow } = boxShadows;
  const { pxToRem, boxShadow } = functions;
  const { size: fontSize } = typography;
  const { borderRadius } = borders;

  // styles for the input with size="small"
  const smallStyles = () => ({
    fontSize: fontSize.xs,
    padding: `${pxToRem(4)} ${pxToRem(12)}`,
  });

  // styles for the input with size="large"
  const largeStyles = () => ({
    padding: pxToRem(12),
  });

  // styles for the focused state of the input
  let focusedBorderColorValue = inputColors.borderColor.focus;

  if (error) {
    focusedBorderColorValue = inputColors.error;
  } else if (success) {
    focusedBorderColorValue = inputColors.success;
  }

  let focusedPaddingLeftValue;
  let focusedPaddingRightValue;

  if (direction === 'ltr') {
    focusedPaddingLeftValue = iconDirection === 'left' ? pxToRem(40) : pxToRem(12);
    focusedPaddingRightValue = iconDirection === 'right' ? pxToRem(40) : pxToRem(12);
  } else {
    focusedPaddingLeftValue = iconDirection === 'left' ? pxToRem(12) : pxToRem(40);
    focusedPaddingRightValue = iconDirection === 'right' ? pxToRem(12) : pxToRem(40);
  }

  let focusedBoxShadowValue = boxShadow([0, 0], [0, 2], inputColors.boxShadow, 1);

  if (error) {
    focusedBoxShadowValue = inputBoxShadow.error;
  } else if (success) {
    focusedBoxShadowValue = inputBoxShadow.success;
  }

  // styles for the input with error={true}
  const errorStyles = () => ({
    backgroundImage:
      "url(\"data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' fill='none' stroke='%23fd5c70' viewBox='0 0 12 12'%3E%3Ccircle cx='6' cy='6' r='4.5'/%3E%3Cpath stroke-linejoin='round' d='M5.8 3.6h.4L6 6.5z'/%3E%3Ccircle cx='6' cy='8.2' r='.6' fill='%23fd5c70' stroke='none'/%3E%3C/svg%3E\")",
    backgroundRepeat: "no-repeat",
    backgroundPosition: `right ${pxToRem(12)} center`,
    backgroundSize: `${pxToRem(16)} ${pxToRem(16)}`,
    borderColor: inputColors.error,
  });

  // styles for the input with success={true}
  const successStyles = () => ({
    backgroundImage:
      "url(\"data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 8'%3E%3Cpath fill='%2366d432' d='M2.3 6.73L.6 4.53c-.4-1.04.46-1.4 1.1-.8l1.1 1.4 3.4-3.8c.6-.63 1.6-.27 1.2.7l-4 4.6c-.43.5-.8.4-1.1.1z'/%3E%3C/svg%3E\")",
    backgroundRepeat: "no-repeat",
    backgroundPosition: `right ${pxToRem(12)} center`,
    backgroundSize: `${pxToRem(16)} ${pxToRem(16)}`,
    borderColor: inputColors.success,
  });

  // styles for the input containing an icon
  const withIconStyles = () => {
    let withIconBorderRadiusValue = borderRadius.md;
    let withIconPaddingLeftValue;
    let withIconPaddingRightValue;

    if (direction === 'ltr') {
      withIconPaddingLeftValue = iconDirection === 'left' ? pxToRem(40) : pxToRem(12);
      withIconPaddingRightValue = iconDirection === 'right' ? pxToRem(40) : pxToRem(12);
    } else {
      withIconPaddingLeftValue = iconDirection === 'left' ? pxToRem(12) : pxToRem(40);
      withIconPaddingRightValue = iconDirection === 'right' ? pxToRem(12) : pxToRem(40);
    }

    return {
      borderRadius: withIconBorderRadiusValue,
      paddingLeft: withIconPaddingLeftValue,
      paddingRight: withIconPaddingRightValue,
    };
  };

  return {
    backgroundColor: disabled ? `${grey[200]} !important` : white.main,
    pointerEvents: disabled ? 'none' : 'auto',
    ...(size === 'small' && smallStyles()),
    ...(size === 'large' && largeStyles()),
    ...(error && errorStyles()),
    ...(success && successStyles()),
    ...(icon && withIconStyles()),

    '& .MuiInputBase-input': {
      height: pxToRem(20),
      color: dark.main,
      fontSize: fontSize.sm,
      fontWeight: typography.fontWeightRegular,
      transition: transitions.create(['border-color', 'box-shadow']),
    },

    '&:hover:not(.Mui-disabled)': {
      backgroundColor: transparent.main,
    },

    '&.Mui-focused': {
      backgroundColor: transparent.main,
      borderColor: focusedBorderColorValue,
      paddingLeft: focusedPaddingLeftValue,
      paddingRight: focusedPaddingRightValue,
      boxShadow: focusedBoxShadowValue,

      '& .MuiInputBase-input': {
        borderColor: focusedBorderColorValue,
      },
    },

    '&.Mui-disabled': {
      backgroundColor: `${grey[200]} !important`,
    },
  };
});

const SoftInputWithIconRoot = styled('div')<{ ownerState: { error: boolean; success: boolean; disabled: boolean } }>(
  ({ theme, ownerState }) => {
    const { palette, functions } = theme as WorkSphereTheme;
    const { error, success, disabled } = ownerState;

    const { inputColors, grey, white } = palette;
    const { pxToRem } = functions;

    return {
      display: 'flex',
      alignItems: 'center',
      backgroundColor: disabled ? grey[200] : white.main,
      border: `${pxToRem(1)} solid`,
      borderRadius: borderRadius.md,
      borderColor: error ? inputColors.error : success ? inputColors.success : inputColors.borderColor.main,
    };
  }
);

const SoftInputIconBoxRoot = styled('div')<{ ownerState: { size: Size } }>(({ theme, ownerState }) => {
  const { functions } = theme as WorkSphereTheme;
  const { pxToRem } = functions;
  const { size } = ownerState;

  return {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: pxToRem(size === 'small' ? 32 : size === 'large' ? 48 : 40),
    height: '100%',
  };
});

const SoftInputIconRoot = styled('i')<{ ownerState: { size: Size } }>(({ theme, ownerState }) => {
  const { typography } = theme as WorkSphereTheme;
  const { size } = ownerState;

  return {
    fontStyle: 'normal',
    lineHeight: 0,
    fontSize: size === 'small' ? typography.size.sm : typography.size.md,
  };
});

const SoftInput = forwardRef<HTMLInputElement, SoftInputProps>(
  ({ size = 'medium', icon, error = false, success = false, disabled = false, ...rest }, ref) => {
    const direction = 'ltr'; // This could be from a context or prop

    if (icon?.component && icon.direction === 'left') {
      return (
        <SoftInputWithIconRoot ownerState={{ error, success, disabled }}>
          <SoftInputIconBoxRoot ownerState={{ size }}>
            <SoftInputIconRoot ownerState={{ size }}>
              {icon.component}
            </SoftInputIconRoot>
          </SoftInputIconBoxRoot>
          <SoftInputRoot
            {...rest}
            ref={ref}
            ownerState={{ size, error, success, iconDirection: icon.direction, direction, disabled }}
          />
        </SoftInputWithIconRoot>
      );
    } else if (icon?.component && icon.direction === 'right') {
      return (
        <SoftInputWithIconRoot ownerState={{ error, success, disabled }}>
          <SoftInputRoot
            {...rest}
            ref={ref}
            ownerState={{ size, error, success, iconDirection: icon.direction, direction, disabled }}
          />
          <SoftInputIconBoxRoot ownerState={{ size }}>
            <SoftInputIconRoot ownerState={{ size }}>
              {icon.component}
            </SoftInputIconRoot>
          </SoftInputIconBoxRoot>
        </SoftInputWithIconRoot>
      );
    }

    return (
      <SoftInputRoot
        {...rest}
        ref={ref}
        ownerState={{ size, error, success, iconDirection: undefined, direction, disabled }}
      />
    );
  }
);

SoftInput.displayName = 'SoftInput';

export default SoftInput;

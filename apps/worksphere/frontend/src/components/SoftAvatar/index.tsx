import { forwardRef } from 'react';
import { Avatar, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';

// Types
type BgColor = 'transparent' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';
type Size = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl';
type Shadow = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl' | 'inset';

interface SoftAvatarProps {
  bgColor?: BgColor;
  size?: Size;
  shadow?: Shadow;
  [key: string]: any; // for other Avatar props
}

interface OwnerState {
  shadow: Shadow;
  bgColor: BgColor;
  size: Size;
}

const SoftAvatarRoot = styled(Avatar, {
  shouldForwardProp: (prop) => !['bgColor', 'size', 'shadow'].includes(String(prop)),
})<{ ownerState: OwnerState }>(({ theme, ownerState }) => {
  const { palette, functions, typography, boxShadows } = theme as WorkSphereTheme;
  const { shadow, bgColor, size } = ownerState;

  const { gradients, transparent } = palette;
  const { pxToRem, linearGradient } = functions;
  const { size: fontSize, fontWeightBold } = typography;

  // backgroundImage value
  const backgroundValue =
    bgColor === 'transparent'
      ? transparent.main
      : linearGradient(gradients[bgColor].main, gradients[bgColor].state, '180deg');

  // size value
  let sizeValue;

  switch (size) {
    case 'xs':
      sizeValue = {
        width: pxToRem(24),
        height: pxToRem(24),
        fontSize: fontSize.xs,
      };
      break;
    case 'sm':
      sizeValue = {
        width: pxToRem(36),
        height: pxToRem(36),
        fontSize: fontSize.sm,
      };
      break;
    case 'lg':
      sizeValue = {
        width: pxToRem(58),
        height: pxToRem(58),
        fontSize: fontSize.sm,
      };
      break;
    case 'xl':
      sizeValue = {
        width: pxToRem(74),
        height: pxToRem(74),
        fontSize: fontSize.md,
      };
      break;
    case 'xxl':
      sizeValue = {
        width: pxToRem(110),
        height: pxToRem(110),
        fontSize: fontSize.md,
      };
      break;
    default:
      sizeValue = {
        width: pxToRem(48),
        height: pxToRem(48),
        fontSize: fontSize.md,
      };
  }

  return {
    background: backgroundValue,
    boxShadow: boxShadows[shadow],
    fontWeight: fontWeightBold,
    ...sizeValue,

    '&.MuiAvatar-root': {
      transition: 'all 200ms ease-in-out',
    },
  };
});

const SoftAvatar = forwardRef<HTMLDivElement, SoftAvatarProps>(
  ({ bgColor = 'transparent', size = 'md', shadow = 'none', ...rest }, ref) => (
    <SoftAvatarRoot ref={ref} ownerState={{ shadow, bgColor, size }} {...rest} />
  )
);

SoftAvatar.displayName = 'SoftAvatar';

export default SoftAvatar;

import { FC, forwardRef } from 'react';
import { Avatar, AvatarProps } from '@mui/material';
import { WorkSphereTheme } from '../../theme';

// Types
type BgColor = 'transparent' | 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';
type Size = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl';
type Shadow = 'none' | 'xs' | 'sm' | 'md' | 'lg' | 'xl' | 'xxl' | 'inset';

interface SoftAvatarProps extends AvatarProps {
  bgColor?: BgColor;
  size?: Size;
  shadow?: Shadow;
}

const SoftAvatar: FC<SoftAvatarProps> = forwardRef(({ bgColor, size, shadow, ...rest }, ref) => {
  const sizes: { [key: string]: { width: string; height: string; fontSize: string } } = {
    xs: { width: '24px', height: '24px', fontSize: '0.75rem' },
    sm: { width: '36px', height: '36px', fontSize: '0.875rem' },
    md: { width: '48px', height: '48px', fontSize: '1rem' },
    lg: { width: '58px', height: '58px', fontSize: '1.125rem' },
    xl: { width: '74px', height: '74px', fontSize: '1.25rem' },
    xxl: { width: '110px', height: '110px', fontSize: '1.5rem' },
  };

  return (
    <Avatar
      ref={ref}
      {...rest}
      sx={{
        ...(size && sizes[size]),
        ...(bgColor && {
          backgroundColor: ({ palette: { [bgColor]: color } }) => color?.main || 'transparent',
          color: ({ palette: { [bgColor]: color } }) =>
            color?.contrastText || 'inherit',
        }),
        ...(shadow && {
          boxShadow: ({ boxShadows: { [shadow]: boxShadow } }) => boxShadow,
        }),
        ...rest.sx,
      }}
    />
  );
});

SoftAvatar.displayName = 'SoftAvatar';

export default SoftAvatar;

import { forwardRef, ReactNode } from 'react';
import { Badge, Box } from '@mui/material';
import { WorkSphereTheme } from '../../theme';
import { useTheme } from '@mui/material/styles';

// Types
type Color = 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';
type Variant = 'gradient' | 'contained' | 'outlined';
type Size = 'xs' | 'sm' | 'md' | 'lg';

interface SoftBadgeProps {
  color?: Color;
  variant?: Variant;
  size?: Size;
  children?: ReactNode;
  badgeContent?: ReactNode;
  [key: string]: any;
}

const SoftBadge = forwardRef<HTMLDivElement, SoftBadgeProps>(
  (
    {
      color = 'info',
      variant = 'contained',
      size = 'sm',
      children,
      badgeContent,
      sx = {},
      ...rest
    },
    ref
  ) => {
    const theme = useTheme<WorkSphereTheme>();
    const { palette, functions } = theme;
    const { gradients, badgeColors, white } = palette;
    const { linearGradient } = functions;

    // Get badge styles based on variant
    const getBadgeStyles = () => {
      const baseStyles = {
        padding: size === 'xs' ? '0.45em 0.775em' : '0.55em 0.9em',
        fontSize: size === 'xs' ? '0.65rem' : '0.75rem',
        fontWeight: 700,
        textTransform: 'uppercase' as const,
        lineHeight: 1,
        position: 'relative' as const,
        transform: 'none',
        marginLeft: 0,
        marginRight: 0,
      };

      if (variant === 'gradient') {
        // Get gradient values from theme
        const gradientMain = gradients[color as keyof typeof gradients]?.main || white.main;
        const gradientState = gradients[color as keyof typeof gradients]?.state || white.main;

        return {
          ...baseStyles,
          background: linearGradient(
            'to right',
            gradientMain,
            gradientState
          ),
          color: white.main,
          border: 'none',
        };
      }

      if (variant === 'outlined') {
        return {
          ...baseStyles,
          background: 'transparent',
          border: `1px solid ${badgeColors[color as keyof typeof badgeColors].background}`,
          color: badgeColors[color as keyof typeof badgeColors].background,
        };
      }

      // Default contained variant
      return {
        ...baseStyles,
        background: badgeColors[color as keyof typeof badgeColors].background,
        color: badgeColors[color as keyof typeof badgeColors].text,
        border: 'none',
      };
    };

    return (
      <Box 
        ref={ref}
        sx={{ 
          display: 'inline-flex',
          alignItems: 'center',
          ...sx
        }}
      >
        <Box
          sx={{
            ...getBadgeStyles(),
            borderRadius: '1rem',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            minWidth: '1rem',
            height: 'auto',
            padding: '0.45em 0.775em',
          }}
        >
          {badgeContent}
        </Box>
      </Box>
    );
  }
);

SoftBadge.displayName = 'SoftBadge';

export default SoftBadge;

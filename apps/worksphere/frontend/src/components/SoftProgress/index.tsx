import { FC, forwardRef } from 'react';
import { LinearProgress, LinearProgressProps } from '@mui/material';
import { WorkSphereTheme } from '../../theme';
import SoftTypography from '../SoftTypography';

// Types
type Color = 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';
type Variant = 'contained' | 'gradient';

interface SoftProgressProps extends LinearProgressProps {
  variant?: Variant;
  color?: Color;
  value: number;
  label?: boolean;
}

interface OwnerState {
  color: Color;
  value: number;
  variant: Variant;
}

const SoftProgress: FC<SoftProgressProps> = forwardRef(
  ({ variant = 'contained', color = 'info', value, label = true, ...rest }, ref) => {
    return (
      <LinearProgress
        ref={ref}
        variant="determinate"
        value={value}
        {...rest}
        sx={{
          height: 6,
          borderRadius: 3,
          '& .MuiLinearProgress-bar': {
            borderRadius: 3,
            ...(variant === 'gradient' && {
              background: ({ palette: { [color]: colorValue }, functions: { linearGradient } }) =>
                linearGradient(colorValue.main, colorValue.state),
            }),
          },
          ...(variant === 'contained' && {
            background: ({ palette: { [color]: colorValue, grey } }) =>
              color === 'light' ? grey[300] : colorValue.main,
          }),
          ...rest.sx,
        }}
      />
    );
  }
);

SoftProgress.displayName = 'SoftProgress';

export default SoftProgress;

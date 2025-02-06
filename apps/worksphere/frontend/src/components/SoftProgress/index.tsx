import { forwardRef } from 'react';
import { LinearProgress, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';
import SoftTypography from '../SoftTypography';

// Types
type Color = 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';
type Variant = 'contained' | 'gradient';

interface SoftProgressProps {
  variant?: Variant;
  color?: Color;
  value?: number;
  label?: boolean;
  [key: string]: any; // for other LinearProgress props
}

interface OwnerState {
  color: Color;
  value: number;
  variant: Variant;
}

const SoftProgressRoot = styled(LinearProgress, {
  shouldForwardProp: (prop) => !['color', 'value', 'variant'].includes(String(prop)),
})<{ ownerState: OwnerState }>(({ theme, ownerState }) => {
  const { palette, functions } = theme as WorkSphereTheme;
  const { color, value, variant } = ownerState;

  const { text, gradients } = palette;
  const { linearGradient } = functions;

  // background value
  let backgroundValue;

  if (variant === 'gradient') {
    backgroundValue = gradients[color]
      ? linearGradient(gradients[color].main, gradients[color].state, '180deg')
      : linearGradient(gradients.info.main, gradients.info.state, '180deg');
  } else {
    backgroundValue = palette[color]?.main || palette.info.main;
  }

  return {
    '& .MuiLinearProgress-bar': {
      background: backgroundValue,
      width: `${value}%`,
      color: text.main,
    },
  };
});

const SoftProgress = forwardRef<HTMLSpanElement, SoftProgressProps>(
  ({ variant = 'contained', color = 'info', value = 0, label = false, ...rest }, ref) => (
    <>
      {label && (
        <SoftTypography variant="button" fontWeight="medium" color="text">
          {value}%
        </SoftTypography>
      )}
      <SoftProgressRoot
        {...rest}
        ref={ref}
        variant="determinate"
        value={value}
        ownerState={{ color, value, variant }}
      />
    </>
  )
);

SoftProgress.displayName = 'SoftProgress';

export default SoftProgress;

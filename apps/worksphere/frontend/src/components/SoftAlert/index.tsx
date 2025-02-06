import { useState, ReactNode } from 'react';
import { Box, Fade, styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';
import SoftBox from '../SoftBox';

// Types
type Color = 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';

interface SoftAlertProps {
  color?: Color;
  dismissible?: boolean;
  children?: ReactNode;
  [key: string]: any; // for other Box props
}

interface OwnerState {
  color: Color;
}

const SoftAlertRoot = styled(Box, {
  shouldForwardProp: (prop) => !['color'].includes(String(prop)),
})<{ ownerState: OwnerState }>(({ theme, ownerState }) => {
  const { palette, typography, borders, functions } = theme as WorkSphereTheme;
  const { color } = ownerState;

  const { white, alertColors } = palette;
  const { fontSizeRegular, fontWeightMedium } = typography;
  const { borderWidth, borderRadius } = borders;
  const { pxToRem, linearGradient } = functions;

  // backgroundImage value
  const backgroundImageValue = alertColors[color]
    ? linearGradient(alertColors[color].main, alertColors[color].state, '180deg')
    : linearGradient(alertColors.info.main, alertColors.info.state, '180deg');

  // border value
  const borderValue = alertColors[color]
    ? `${borderWidth[1]} solid ${alertColors[color].border}`
    : `${borderWidth[1]} solid ${alertColors.info.border}`;

  return {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    minHeight: pxToRem(60),
    backgroundImage: backgroundImageValue,
    color: white.main,
    position: 'relative',
    padding: pxToRem(16),
    marginBottom: pxToRem(16),
    border: borderValue,
    borderRadius: borderRadius.md,
    fontSize: fontSizeRegular,
    fontWeight: fontWeightMedium,
  };
});

const SoftAlertCloseIcon = styled('span')(({ theme }) => {
  const { palette, typography, functions, transitions } = theme as WorkSphereTheme;

  const { white } = palette;
  const { size, fontWeightMedium } = typography;
  const { pxToRem } = functions;

  return {
    color: white.main,
    fontSize: size.xl,
    padding: `${pxToRem(9)} ${pxToRem(6)} ${pxToRem(8)}`,
    marginLeft: pxToRem(40),
    fontWeight: fontWeightMedium,
    opacity: 0.5,
    cursor: 'pointer',
    lineHeight: 0,
    transition: transitions.create('opacity', {
      easing: transitions.easing.easeInOut,
      duration: transitions.duration.shorter,
    }),

    '&:hover': {
      opacity: 1,
    },
  };
});

const SoftAlert = ({ color = 'info', dismissible = false, children, ...rest }: SoftAlertProps) => {
  const [alertStatus, setAlertStatus] = useState<'mount' | 'fadeOut'>('mount');

  const handleAlertStatus = () => setAlertStatus('fadeOut');

  // The base template for the alert
  const alertTemplate = (mount = true) => (
    <Fade in={mount} timeout={300}>
      <SoftAlertRoot ownerState={{ color }} {...rest}>
        <SoftBox display="flex" alignItems="center" color="white">
          {children}
        </SoftBox>
        {dismissible ? (
          <SoftAlertCloseIcon onClick={mount ? handleAlertStatus : undefined}>
            &times;
          </SoftAlertCloseIcon>
        ) : null}
      </SoftAlertRoot>
    </Fade>
  );

  return alertStatus === 'mount' ? alertTemplate() : alertTemplate(false);
};

export default SoftAlert;

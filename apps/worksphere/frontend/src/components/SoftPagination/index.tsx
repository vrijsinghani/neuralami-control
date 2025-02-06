import { forwardRef, createContext, useContext, useMemo, ReactNode } from 'react';
import { styled } from '@mui/material';
import { WorkSphereTheme } from '../../theme';
import SoftBox from '../SoftBox';
import SoftButton from '../SoftButton';

// Types
type Color = 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error' | 'light' | 'dark';
type Variant = 'gradient' | 'contained';
type Size = 'small' | 'medium' | 'large';

interface PaginationContextType {
  variant: Variant;
  color: Color;
  size: Size;
}

interface SoftPaginationProps {
  item?: boolean;
  variant?: Variant;
  color?: Color;
  size?: Size;
  active?: boolean;
  children?: ReactNode;
  [key: string]: any; // for other props
}

interface OwnerState {
  variant: Variant;
  active: boolean;
  paginationSize: Size | null;
}

// The Pagination main context
const Context = createContext<PaginationContextType | null>(null);

const SoftPaginationItemRoot = styled(SoftButton, {
  shouldForwardProp: (prop) => !['variant', 'active', 'paginationSize'].includes(String(prop)),
})<{ ownerState: OwnerState }>(({ theme, ownerState }) => {
  const { borders, functions, typography, palette } = theme as WorkSphereTheme;
  const { variant, paginationSize, active } = ownerState;

  const { borderColor } = borders;
  const { pxToRem } = functions;
  const { fontWeightRegular, size: fontSize } = typography;
  const { light } = palette;

  // width, height, minWidth and minHeight values
  let sizeValue = pxToRem(36);

  if (paginationSize === 'small') {
    sizeValue = pxToRem(30);
  } else if (paginationSize === 'large') {
    sizeValue = pxToRem(46);
  }

  return {
    borderColor,
    margin: `0 ${pxToRem(2)}`,
    pointerEvents: active ? 'none' : 'auto',
    fontWeight: fontWeightRegular,
    fontSize: fontSize.sm,
    width: sizeValue,
    minWidth: sizeValue,
    height: sizeValue,
    minHeight: sizeValue,

    '&:hover, &:focus, &:active': {
      transform: 'none',
      boxShadow: 'none',
      backgroundColor: light.main,
      borderColor,
    },
  };
});

const SoftPagination = forwardRef<HTMLDivElement, SoftPaginationProps>(
  ({ item = false, variant = 'gradient', color = 'info', size = 'medium', active = false, children, ...rest }, ref) => {
    const context = item ? useContext(Context) : null;
    const paginationSize = context ? context.size : null;
    const value = useMemo(() => ({ variant, color, size }), [variant, color, size]);

    return (
      <Context.Provider value={value}>
        {item ? (
          <SoftPaginationItemRoot
            {...rest}
            ref={ref}
            variant={active ? context?.variant || 'gradient' : 'outlined'}
            color={active ? context?.color || 'info' : 'secondary'}
            iconOnly
            circular
            ownerState={{ variant, active, paginationSize }}
          >
            {children}
          </SoftPaginationItemRoot>
        ) : (
          <SoftBox
            display="flex"
            justifyContent="flex-end"
            alignItems="center"
            sx={{ listStyle: 'none' }}
          >
            {children}
          </SoftBox>
        )}
      </Context.Provider>
    );
  }
);

SoftPagination.displayName = 'SoftPagination';

export default SoftPagination;

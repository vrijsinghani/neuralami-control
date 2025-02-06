import { FC, ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

// @mui material components
import { Box, useTheme } from '@mui/material';

interface DashboardLayoutProps {
  children: ReactNode;
}

const DashboardLayout: FC<DashboardLayoutProps> = ({ children }) => {
  const { pathname } = useLocation();
  const theme = useTheme();

  return (
    <Box
      sx={{
        p: 3,
        position: 'relative',
        minHeight: '100vh',
        backgroundColor: theme.palette.background.default,
        '&:after': {
          content: '""',
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          backgroundImage: `linear-gradient(195deg, ${theme.palette.primary.main}, ${theme.palette.primary.dark})`,
          opacity: 0.1,
          zIndex: -1,
        },
      }}
    >
      {children}
    </Box>
  );
};

export default DashboardLayout; 
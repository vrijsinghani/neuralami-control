import { Box } from '@mui/material';
import PropTypes from 'prop-types';
import Sidebar from '../../components/Sidebar';
import Navbar from '../../components/Navbar';

function DashboardLayout({ children }) {
  return (
    <Box
      sx={{
        display: 'flex',
        minHeight: '100vh',
        bgcolor: 'background.default',
        overflowX: 'hidden',
      }}
    >
      <Sidebar />
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          pl: { sm: 3 },
          pr: { xs: 2, sm: 3 },
          pt: { xs: 8, sm: 3 },
          pb: { xs: 2, sm: 3 },
          width: { sm: `calc(100% - 228px)` },
          overflowX: 'hidden',
        }}
      >
        <Navbar />
        <Box sx={{ mt: 3 }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}

DashboardLayout.propTypes = {
  children: PropTypes.node.isRequired,
};

export default DashboardLayout; 
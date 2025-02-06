import { FC, useState } from 'react';
import { Link } from 'react-router-dom';

// @mui material components
import { 
  AppBar, 
  Toolbar, 
  IconButton, 
  Menu, 
  MenuItem, 
  Icon,
  Box,
  useTheme
} from '@mui/material';

// Custom components
import SoftBox from '../../SoftBox';
import SoftTypography from '../../SoftTypography';

const DashboardNavbar: FC = () => {
  const [openMenu, setOpenMenu] = useState<null | HTMLElement>(null);
  const theme = useTheme();

  const handleOpenMenu = (event: React.MouseEvent<HTMLElement>) => {
    setOpenMenu(event.currentTarget);
  };

  const handleCloseMenu = () => {
    setOpenMenu(null);
  };

  return (
    <AppBar
      position="sticky"
      color="inherit"
      sx={{
        width: '100%',
        backgroundColor: theme.palette.background.paper,
        boxShadow: theme.shadows[4],
        backdropFilter: 'saturate(200%) blur(30px)',
      }}
    >
      <Toolbar sx={{ minHeight: '70px' }}>
        <SoftBox
          color="inherit"
          mb={{ xs: 1, md: 0 }}
          sx={({ breakpoints }) => ({
            [breakpoints.down('md')]: {
              display: 'flex',
              alignItems: 'center',
              width: '100%',
              justifyContent: 'space-between',
            },
          })}
        >
          <SoftBox component={Link} to="/" display="flex" alignItems="center">
            <SoftTypography variant="h6" fontWeight="medium" color="dark">
              WorkSphere
            </SoftTypography>
          </SoftBox>

          <Box sx={{ flexGrow: 1 }} />

          <IconButton
            size="large"
            color="inherit"
            aria-controls="notification-menu"
            aria-haspopup="true"
            onClick={handleOpenMenu}
          >
            <Icon>notifications</Icon>
          </IconButton>

          <Menu
            id="notification-menu"
            anchorEl={openMenu}
            open={Boolean(openMenu)}
            onClose={handleCloseMenu}
            anchorOrigin={{
              vertical: 'bottom',
              horizontal: 'right',
            }}
            transformOrigin={{
              vertical: 'top',
              horizontal: 'right',
            }}
          >
            <MenuItem onClick={handleCloseMenu}>Notification 1</MenuItem>
            <MenuItem onClick={handleCloseMenu}>Notification 2</MenuItem>
            <MenuItem onClick={handleCloseMenu}>Notification 3</MenuItem>
          </Menu>

          <IconButton
            size="large"
            color="inherit"
            sx={{ ml: 1 }}
          >
            <Icon>person</Icon>
          </IconButton>
        </SoftBox>
      </Toolbar>
    </AppBar>
  );
};

export default DashboardNavbar; 
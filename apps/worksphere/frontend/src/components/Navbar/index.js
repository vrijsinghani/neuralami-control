import { useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import {
  AppBar,
  Box,
  IconButton,
  Toolbar,
  Typography,
  Menu,
  MenuItem,
  Avatar,
  InputBase,
  Badge,
  Breadcrumbs,
  useTheme,
  Button,
} from '@mui/material';
import {
  Search as SearchIcon,
  Notifications as NotificationsIcon,
  Settings as SettingsIcon,
  Person as PersonIcon,
  Logout as LogoutIcon,
  NavigateNext as NavigateNextIcon,
  Home as HomeIcon,
} from '@mui/icons-material';

// Routes
import routes from '../../routes';

function Navbar() {
  const theme = useTheme();
  const location = useLocation();
  const [anchorEl, setAnchorEl] = useState(null);
  const [notificationsAnchor, setNotificationsAnchor] = useState(null);

  const handleProfileClick = (event) => {
    setAnchorEl(event.currentTarget);
  };

  const handleNotificationsClick = (event) => {
    setNotificationsAnchor(event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
    setNotificationsAnchor(null);
  };

  // Find current route for breadcrumbs
  const currentRoute = routes.find((route) => route.route === location.pathname);

  return (
    <AppBar
      position="relative"
      color="transparent"
      sx={{
        backdropFilter: 'saturate(200%) blur(30px)',
        backgroundColor: 'rgba(255, 255, 255, 0.8)',
        boxShadow: 'none',
        borderRadius: '1rem',
        py: 0.5,
        px: { xs: 2, sm: 3 },
        mx: { sm: 3 },
        mt: 2,
      }}
    >
      <Toolbar sx={{ minHeight: { xs: 64, sm: 62 }, px: 0 }}>
        {/* Breadcrumbs */}
        <Box display="flex" alignItems="center" flexGrow={1}>
          <Box display="flex" alignItems="center" mr={1}>
            <IconButton
              component={Link}
              to="/"
              sx={{
                p: 1.25,
                background: (theme) => `linear-gradient(310deg, ${theme.palette.info.main}, ${theme.palette.info.dark})`,
                color: 'white',
                borderRadius: '0.5rem',
                boxShadow: '0 3px 6px 0 rgba(20, 23, 39, 0.08)',
                '&:hover': {
                  boxShadow: '0 4px 8px 0 rgba(20, 23, 39, 0.15)',
                },
                minWidth: 32,
                minHeight: 32,
              }}
            >
              <HomeIcon sx={{ fontSize: '1rem' }} />
            </IconButton>
          </Box>
          <Box>
            <Typography
              variant="h6"
              component="h6"
              sx={{
                fontSize: '1rem',
                fontWeight: 700,
                color: 'text.primary',
                lineHeight: 1.625,
              }}
            >
              {currentRoute?.name || 'Dashboard'}
            </Typography>
          </Box>
        </Box>

        {/* Search Bar */}
        <Box
          sx={{
            position: 'relative',
            borderRadius: '0.5rem',
            bgcolor: 'transparent',
            border: '1px solid',
            borderColor: 'grey.300',
            mr: 2,
            width: 'auto',
            transition: 'box-shadow 150ms ease, border-color 150ms ease',
            '&:hover': {
              borderColor: 'grey.400',
            },
            '&:focus-within': {
              borderColor: 'primary.main',
              boxShadow: '0 0 0 2px rgba(203, 12, 159, 0.2)',
            },
          }}
        >
          <Box sx={{ py: 0.75, px: 1.5, display: 'flex', alignItems: 'center' }}>
            <SearchIcon sx={{ color: 'text.secondary', fontSize: '1rem' }} />
            <InputBase
              placeholder="Type here..."
              sx={{ 
                ml: 1,
                fontSize: '0.875rem',
                color: 'text.primary',
                '& .MuiInputBase-input': {
                  p: '0',
                  '&::placeholder': {
                    color: 'text.secondary',
                    opacity: 1,
                  },
                },
              }}
            />
          </Box>
        </Box>

        {/* Notifications */}
        <IconButton
          onClick={handleNotificationsClick}
          sx={{
            mr: 1,
            p: 1,
            color: 'text.secondary',
            '&:hover': { 
              color: 'text.primary',
              bgcolor: 'transparent',
            },
          }}
        >
          <Badge 
            badgeContent={4} 
            color="error"
            sx={{
              '& .MuiBadge-badge': {
                bgcolor: 'error.main',
                boxShadow: '0 0 6px 0 rgba(234, 6, 6, 0.7)',
                minWidth: 18,
                height: 18,
                padding: '0 5px',
                fontSize: '0.75rem',
              },
            }}
          >
            <NotificationsIcon sx={{ fontSize: '1.25rem' }} />
          </Badge>
        </IconButton>
        <Menu
          anchorEl={notificationsAnchor}
          open={Boolean(notificationsAnchor)}
          onClose={handleClose}
          PaperProps={{
            sx: {
              width: 320,
              maxHeight: 480,
              mt: 1.5,
              boxShadow: '0 8px 26px -4px rgba(20,20,20,0.15), 0 8px 9px -5px rgba(20,20,20,0.06)',
              borderRadius: '0.5rem',
              border: '1px solid',
              borderColor: 'grey.200',
            },
          }}
          transformOrigin={{ horizontal: 'right', vertical: 'top' }}
          anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
        >
          <MenuItem sx={{ py: 1.5 }}>
            <Box>
              <Typography variant="subtitle2" fontWeight="bold">
                New message received
              </Typography>
              <Typography variant="caption" color="text.secondary">
                2 min ago
              </Typography>
            </Box>
          </MenuItem>
          <MenuItem sx={{ py: 1.5 }}>
            <Box>
              <Typography variant="subtitle2" fontWeight="bold">
                Project update available
              </Typography>
              <Typography variant="caption" color="text.secondary">
                1 hour ago
              </Typography>
            </Box>
          </MenuItem>
        </Menu>

        {/* Profile Menu */}
        <Button
          onClick={handleProfileClick}
          sx={{
            py: 0.75,
            px: 1,
            borderRadius: '0.5rem',
            color: 'text.primary',
            '&:hover': { 
              bgcolor: 'grey.100',
            },
          }}
        >
          <Avatar
            sx={{
              width: 32,
              height: 32,
              bgcolor: 'info.main',
              background: (theme) => `linear-gradient(310deg, ${theme.palette.info.main}, ${theme.palette.info.dark})`,
              boxShadow: '0 2px 6px 0 rgba(20, 23, 39, 0.08)',
              fontSize: '0.875rem',
              fontWeight: 600,
            }}
          >
            U
          </Avatar>
          <Box ml={1} textAlign="left">
            <Typography 
              variant="button" 
              sx={{ 
                fontSize: '0.875rem',
                fontWeight: 600,
                lineHeight: 1.3,
                display: 'block',
              }}
            >
              User Name
            </Typography>
            <Typography 
              variant="caption" 
              sx={{ 
                color: 'text.secondary',
                fontSize: '0.75rem',
                lineHeight: 1.25,
              }}
            >
              Admin
            </Typography>
          </Box>
        </Button>
        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={handleClose}
          PaperProps={{
            sx: {
              width: 200,
              mt: 1.5,
              boxShadow: '0 8px 26px -4px rgba(20,20,20,0.15), 0 8px 9px -5px rgba(20,20,20,0.06)',
              borderRadius: '0.5rem',
              border: '1px solid',
              borderColor: 'grey.200',
            },
          }}
          transformOrigin={{ horizontal: 'right', vertical: 'top' }}
          anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
        >
          <MenuItem onClick={handleClose} sx={{ py: 1.5 }}>
            <PersonIcon sx={{ mr: 2, fontSize: '1.25rem', color: 'text.secondary' }} />
            <Typography variant="button" sx={{ fontSize: '0.875rem', fontWeight: 500 }}>
              Profile
            </Typography>
          </MenuItem>
          <MenuItem onClick={handleClose} sx={{ py: 1.5 }}>
            <SettingsIcon sx={{ mr: 2, fontSize: '1.25rem', color: 'text.secondary' }} />
            <Typography variant="button" sx={{ fontSize: '0.875rem', fontWeight: 500 }}>
              Settings
            </Typography>
          </MenuItem>
          <MenuItem onClick={handleClose} sx={{ py: 1.5 }}>
            <LogoutIcon sx={{ mr: 2, fontSize: '1.25rem', color: 'text.secondary' }} />
            <Typography variant="button" sx={{ fontSize: '0.875rem', fontWeight: 500 }}>
              Logout
            </Typography>
          </MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
}

export default Navbar; 
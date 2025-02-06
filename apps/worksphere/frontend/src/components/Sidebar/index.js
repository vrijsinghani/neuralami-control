import { useState } from 'react';
import { useLocation, Link } from 'react-router-dom';
import {
  Box,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Typography,
  useTheme,
  useMediaQuery,
  Divider,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';

// Routes
import routes from '../../routes';

const drawerWidth = 228;

function Sidebar() {
  const theme = useTheme();
  const location = useLocation();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleDrawerToggle = () => {
    setMobileOpen(!mobileOpen);
  };

  const drawer = (
    <>
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          p: 3,
        }}
      >
        <Box display="flex" alignItems="center">
          <Box
            component="img"
            src="/static/images/logo-ct.png"
            alt="Logo"
            sx={{ width: 32, height: 32, mr: 1 }}
          />
          <Typography 
            variant="h6" 
            sx={{ 
              color: 'text.primary',
              fontWeight: 700,
              letterSpacing: '-0.025em',
              fontSize: '1rem',
              lineHeight: 1.625,
            }}
          >
            Soft UI Dashboard
          </Typography>
        </Box>
        {isMobile && (
          <IconButton onClick={handleDrawerToggle}>
            <ChevronLeftIcon />
          </IconButton>
        )}
      </Box>
      <Divider sx={{ mx: 3, borderColor: 'rgba(0,0,0,0.08)' }} />
      <List sx={{ px: 3, pt: 3 }}>
        {routes.map((route) => {
          const Icon = route.icon;
          const isActive = location.pathname === route.route;

          return (
            <ListItem
              key={route.key}
              component={Link}
              to={route.route}
              onClick={isMobile ? handleDrawerToggle : undefined}
              sx={{
                mb: 1,
                borderRadius: 1.5,
                color: isActive ? 'white' : 'text.secondary',
                bgcolor: isActive ? 'primary.main' : 'transparent',
                '&:hover': {
                  bgcolor: isActive ? 'primary.dark' : 'rgba(0,0,0,0.04)',
                },
                transition: 'all 200ms ease-in-out',
                boxShadow: isActive ? '0 2px 6px 0 rgba(203, 12, 159, 0.4)' : 'none',
                minHeight: 42,
                px: 2,
                py: 1,
                '& .MuiListItemIcon-root': {
                  minWidth: 32,
                  color: isActive ? 'white' : 'text.secondary',
                  mr: 1,
                },
                '& .MuiListItemText-root': {
                  margin: 0,
                },
                '& .MuiTypography-root': {
                  fontSize: '0.875rem',
                  fontWeight: 500,
                },
              }}
            >
              <ListItemIcon>
                <Icon fontSize="small" />
              </ListItemIcon>
              <ListItemText primary={route.name} />
            </ListItem>
          );
        })}
      </List>
    </>
  );

  return (
    <>
      {isMobile && (
        <IconButton
          color="inherit"
          aria-label="open drawer"
          edge="start"
          onClick={handleDrawerToggle}
          sx={{
            position: 'fixed',
            left: 16,
            top: 16,
            zIndex: (theme) => theme.zIndex.drawer + 2,
            bgcolor: 'white',
            boxShadow: '0 2px 12px 0 rgba(0,0,0,0.16)',
            '&:hover': {
              bgcolor: 'white',
            },
            width: 40,
            height: 40,
            borderRadius: '0.5rem',
          }}
        >
          <MenuIcon />
        </IconButton>
      )}
      <Box
        component="nav"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          overflowX: 'hidden',
        }}
      >
        {/* Mobile drawer */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={handleDrawerToggle}
          ModalProps={{
            keepMounted: true,
          }}
          sx={{
            display: { xs: 'block', sm: 'none' },
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              bgcolor: 'background.default',
              borderRight: 'none',
              boxShadow: 'none',
              overflowX: 'hidden',
            },
          }}
        >
          {drawer}
        </Drawer>
        {/* Desktop drawer */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', sm: 'block' },
            '& .MuiDrawer-paper': {
              width: drawerWidth,
              bgcolor: 'background.default',
              borderRight: 'none',
              boxShadow: 'none',
              height: '100%',
              overflowX: 'hidden',
            },
          }}
          open
        >
          {drawer}
        </Drawer>
      </Box>
    </>
  );
}

export default Sidebar; 
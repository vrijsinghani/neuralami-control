import { useEffect } from 'react';
import { useLocation, Routes, Route, Navigate } from 'react-router-dom';

// Components
import Box from '@mui/material/Box';

// Routes
import routes from './routes';

export default function App() {
  const { pathname } = useLocation();

  // Scroll to top when navigating to a new page
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  const getRoutes = (allRoutes) =>
    allRoutes.map((route) => {
      if (route.route) {
        return <Route exact path={route.route} element={route.component} key={route.key} />;
      }
      return null;
    });

  return (
    <Box>
      <Routes>
        {getRoutes(routes)}
        <Route path="*" element={<Navigate to="/dashboard" />} />
      </Routes>
    </Box>
  );
} 
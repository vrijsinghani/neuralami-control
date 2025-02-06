// Views
import Dashboard from '../views/Dashboard';

// Icons
import DashboardIcon from '@mui/icons-material/Dashboard';
import PersonIcon from '@mui/icons-material/Person';
import AssignmentIcon from '@mui/icons-material/Assignment';
import SettingsIcon from '@mui/icons-material/Settings';

const routes = [
  {
    type: "route",
    name: "Dashboard",
    key: "dashboard",
    route: "/dashboard",
    icon: DashboardIcon,
    component: <Dashboard />,
  },
  {
    type: "route",
    name: "Profile",
    key: "profile",
    route: "/profile",
    icon: PersonIcon,
    component: <Dashboard />, // Placeholder until we create the Profile component
  },
  {
    type: "route",
    name: "Projects",
    key: "projects",
    route: "/projects",
    icon: AssignmentIcon,
    component: <Dashboard />, // Placeholder until we create the Projects component
  },
  {
    type: "route",
    name: "Settings",
    key: "settings",
    route: "/settings",
    icon: SettingsIcon,
    component: <Dashboard />, // Placeholder until we create the Settings component
  },
  // Add more routes here as we build them
];

export default routes; 
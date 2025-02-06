import { Grid, Icon, Box, Typography } from '@mui/material';
import DashboardLayout from '../../layouts/DashboardLayout';

// Components
import StatCard from './components/StatCard';
import BuildByDevelopers from './components/BuildByDevelopers';
import WorkWithTheRockets from './components/WorkWithTheRockets';
import Projects from './components/Projects';
import OrderOverview from './components/OrderOverview';
import ReportsBarChart from './components/ReportsBarChart';
import GradientLineChart from './components/GradientLineChart';

// Data
const reportsBarChartData = {
  chart: {
    labels: ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    datasets: {
      label: "Active Users",
      data: [450, 200, 100, 220, 500, 100, 400, 230, 500],
    },
  },
  items: [
    {
      icon: { color: "primary", component: "library_books" },
      label: "users",
      progress: { content: "36K", percentage: 60 },
    },
    {
      icon: { color: "info", component: "touch_app" },
      label: "clicks",
      progress: { content: "2M", percentage: 90 },
    },
    {
      icon: { color: "warning", component: "payment" },
      label: "sales",
      progress: { content: "$435", percentage: 30 },
    },
    {
      icon: { color: "error", component: "extension" },
      label: "items",
      progress: { content: "43", percentage: 50 },
    },
  ],
};

const gradientLineChartData = {
  labels: ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
  datasets: [
    {
      label: "Mobile apps",
      data: [50, 40, 300, 220, 500, 250, 400, 230, 500],
    },
  ],
};

function Dashboard() {
  return (
    <DashboardLayout>
      <Box py={3}>
        {/* Stats Cards */}
        <Box mb={3}>
          <Grid container spacing={3}>
            <Grid item xs={12} sm={6} xl={3}>
              <StatCard
                title="Today's Money"
                count="$53,000"
                percentage={{ color: "success", text: "+55%" }}
                icon={{ color: "info", name: "paid" }}
              />
            </Grid>
            <Grid item xs={12} sm={6} xl={3}>
              <StatCard
                title="Today's Users"
                count="2,300"
                percentage={{ color: "success", text: "+3%" }}
                icon={{ color: "info", name: "public" }}
              />
            </Grid>
            <Grid item xs={12} sm={6} xl={3}>
              <StatCard
                title="New Clients"
                count="+3,462"
                percentage={{ color: "error", text: "-2%" }}
                icon={{ color: "info", name: "emoji_events" }}
              />
            </Grid>
            <Grid item xs={12} sm={6} xl={3}>
              <StatCard
                title="Sales"
                count="$103,430"
                percentage={{ color: "success", text: "+5%" }}
                icon={{ color: "info", name: "shopping_cart" }}
              />
            </Grid>
          </Grid>
        </Box>

        {/* Developer Section */}
        <Box mb={3}>
          <Grid container spacing={3}>
            <Grid item xs={12} lg={7}>
              <BuildByDevelopers />
            </Grid>
            <Grid item xs={12} lg={5}>
              <WorkWithTheRockets />
            </Grid>
          </Grid>
        </Box>

        {/* Charts Section */}
        <Box mb={3}>
          <Grid container spacing={3}>
            <Grid item xs={12} lg={5}>
              <ReportsBarChart
                title="Active Users"
                description={
                  <>
                    (<strong>+23%</strong>) than last week
                  </>
                }
                chart={reportsBarChartData.chart}
                items={reportsBarChartData.items}
              />
            </Grid>
            <Grid item xs={12} lg={7}>
              <GradientLineChart
                title="Sales Overview"
                description={
                  <Box display="flex" alignItems="center">
                    <Box color="success.main" mr={0.5}>
                      <Icon>arrow_upward</Icon>
                    </Box>
                    <Typography variant="button" color="text.secondary" fontWeight="medium">
                      4% more{" "}
                      <Typography component="span" variant="button" color="text.secondary" fontWeight="regular">
                        in 2021
                      </Typography>
                    </Typography>
                  </Box>
                }
                chart={gradientLineChartData}
              />
            </Grid>
          </Grid>
        </Box>

        {/* Projects and Overview Section */}
        <Grid container spacing={3}>
          <Grid item xs={12} md={6} lg={8}>
            <Projects />
          </Grid>
          <Grid item xs={12} md={6} lg={4}>
            <OrderOverview />
          </Grid>
        </Grid>
      </Box>
    </DashboardLayout>
  );
}

export default Dashboard; 
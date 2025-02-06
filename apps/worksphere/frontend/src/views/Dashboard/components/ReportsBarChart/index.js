import PropTypes from 'prop-types';
import { Card, Icon, Typography, Box } from '@mui/material';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

function ReportsBarChart({ title, description, chart, items }) {
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
    },
    scales: {
      y: {
        grid: {
          display: false,
          drawBorder: false,
        },
        ticks: {
          display: true,
          padding: 10,
        },
      },
      x: {
        grid: {
          display: false,
          drawBorder: false,
        },
        ticks: {
          display: true,
          padding: 10,
        },
      },
    },
  };

  const chartData = {
    labels: chart.labels,
    datasets: [
      {
        label: chart.datasets.label,
        data: chart.datasets.data,
        backgroundColor: 'rgba(203, 12, 159, 0.8)',
        borderColor: 'rgba(203, 12, 159, 1)',
        borderWidth: 2,
        borderRadius: 5,
        maxBarThickness: 10,
      },
    ],
  };

  return (
    <Card sx={{ height: '100%' }}>
      <Box p={3}>
        {/* Chart header */}
        <Box mb={3}>
          <Typography variant="h6" color="text.primary">
            {title}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {description}
          </Typography>
        </Box>

        {/* Chart */}
        <Box height={200} mb={2}>
          <Bar options={chartOptions} data={chartData} />
        </Box>

        {/* Items */}
        <Box
          display="grid"
          gridTemplateColumns="repeat(2, 1fr)"
          gap={2}
        >
          {items.map((item) => (
            <Box
              key={item.label}
              display="flex"
              alignItems="center"
              p={1}
            >
              <Box
                display="flex"
                alignItems="center"
                justifyContent="center"
                width={32}
                height={32}
                borderRadius={1}
                bgcolor={item.icon.color + '.lighter'}
                color={item.icon.color + '.main'}
                mr={2}
              >
                <Icon fontSize="small">{item.icon.component}</Icon>
              </Box>
              <Box flexGrow={1}>
                <Typography
                  variant="button"
                  color="text.secondary"
                  fontWeight="medium"
                  textTransform="capitalize"
                >
                  {item.label}
                </Typography>
                <Typography variant="h6" fontWeight="bold">
                  {item.progress.content}
                </Typography>
              </Box>
            </Box>
          ))}
        </Box>
      </Box>
    </Card>
  );
}

ReportsBarChart.propTypes = {
  title: PropTypes.string.isRequired,
  description: PropTypes.node.isRequired,
  chart: PropTypes.shape({
    labels: PropTypes.arrayOf(PropTypes.string).isRequired,
    datasets: PropTypes.shape({
      label: PropTypes.string.isRequired,
      data: PropTypes.arrayOf(PropTypes.number).isRequired,
    }).isRequired,
  }).isRequired,
  items: PropTypes.arrayOf(
    PropTypes.shape({
      icon: PropTypes.shape({
        color: PropTypes.string.isRequired,
        component: PropTypes.string.isRequired,
      }).isRequired,
      label: PropTypes.string.isRequired,
      progress: PropTypes.shape({
        content: PropTypes.string.isRequired,
        percentage: PropTypes.number.isRequired,
      }).isRequired,
    })
  ).isRequired,
};

export default ReportsBarChart; 
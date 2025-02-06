import PropTypes from 'prop-types';
import { Card, Typography, Box } from '@mui/material';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from 'chart.js';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

function GradientLineChart({ title, description, chart }) {
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
    },
    interaction: {
      intersect: false,
      mode: 'index',
    },
    scales: {
      y: {
        grid: {
          drawBorder: false,
          display: true,
          drawOnChartArea: true,
          drawTicks: false,
          borderDash: [5, 5],
        },
        ticks: {
          display: true,
          padding: 10,
          suggestedMin: 0,
          suggestedMax: Math.max(...chart.datasets[0].data) * 1.1,
        },
      },
      x: {
        grid: {
          drawBorder: false,
          display: false,
          drawOnChartArea: false,
          drawTicks: false,
        },
        ticks: {
          display: true,
          padding: 10,
        },
      },
    },
  };

  return (
    <Card sx={{ height: '100%' }}>
      <Box p={3}>
        {/* Chart header */}
        <Box mb={3}>
          <Typography variant="h6" color="text.primary">
            {title}
          </Typography>
          <Box mt={1}>
            {description}
          </Box>
        </Box>

        {/* Chart */}
        <Box height={300}>
          <Line 
            options={chartOptions} 
            data={{
              labels: chart.labels,
              datasets: [
                {
                  label: chart.datasets[0].label,
                  tension: 0.4,
                  borderWidth: 3,
                  pointRadius: 2,
                  pointBackgroundColor: '#cb0c9f',
                  borderColor: '#cb0c9f',
                  borderJoinStyle: 'round',
                  backgroundColor: 'rgba(203,12,159,0.1)',
                  fill: true,
                  data: chart.datasets[0].data,
                },
              ],
            }}
          />
        </Box>
      </Box>
    </Card>
  );
}

GradientLineChart.propTypes = {
  title: PropTypes.string.isRequired,
  description: PropTypes.node.isRequired,
  chart: PropTypes.shape({
    labels: PropTypes.arrayOf(PropTypes.string).isRequired,
    datasets: PropTypes.arrayOf(
      PropTypes.shape({
        label: PropTypes.string.isRequired,
        data: PropTypes.arrayOf(PropTypes.number).isRequired,
      })
    ).isRequired,
  }).isRequired,
};

export default GradientLineChart; 
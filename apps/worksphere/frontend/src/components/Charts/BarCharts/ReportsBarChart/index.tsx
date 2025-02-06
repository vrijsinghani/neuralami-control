import { FC, useRef, useEffect } from 'react';

// @mui material components
import { Card, Icon } from '@mui/material';

// Chart.js
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import { Chart } from 'chart.js/auto';

// Custom components
import SoftBox from '../../../SoftBox';
import SoftTypography from '../../../SoftTypography';

// Chart configurations
import configs from './configs';

// Register ChartJS components
ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

interface ReportsBarChartProps {
  color?: string;
  title: string;
  description?: React.ReactNode;
  chart: {
    labels: string[];
    datasets: {
      label: string;
      data: number[];
    };
  };
  items?: {
    icon: { color: string; component: string };
    label: string;
    progress: { content: string; percentage: number };
  }[];
}

const ReportsBarChart: FC<ReportsBarChartProps> = ({ color = "dark", title, description, chart, items }) => {
  const chartRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstance = useRef<Chart | null>(null);

  useEffect(() => {
    const ctx = chartRef.current?.getContext('2d');

    if (ctx) {
      const chartDatasets = {
        labels: chart.labels,
        datasets: [
          {
            label: chart.datasets.label,
            tension: 0.4,
            borderWidth: 0,
            borderRadius: 4,
            borderSkipped: false,
            backgroundColor: "#fff",
            data: chart.datasets.data,
            maxBarThickness: 6,
          },
        ],
      };

      const { data, options } = configs(chart.labels, chartDatasets);

      // Destroy previous chart instance
      if (chartInstance.current) {
        chartInstance.current.destroy();
      }

      // Create new chart instance
      chartInstance.current = new Chart(ctx, {
        type: 'bar',
        data,
        options,
      });
    }

    // Cleanup function
    return () => {
      if (chartInstance.current) {
        chartInstance.current.destroy();
      }
    };
  }, [chart]);

  const renderItems = items?.map(({ icon, label, progress }) => (
    <SoftBox key={label} px={2}>
      <SoftBox display="flex" py={1} pr={2}>
        <SoftBox
          display="flex"
          justifyContent="center"
          alignItems="center"
          width="2rem"
          height="2rem"
          borderRadius="md"
          color="white"
          bgColor={icon.color}
          variant="gradient"
          mr={2}
        >
          <Icon fontSize="small">{icon.component}</Icon>
        </SoftBox>
        <SoftBox display="flex" flexDirection="column" justifyContent="center">
          <SoftTypography variant="button" fontWeight="medium" color="text">
            {label}
          </SoftTypography>
          <SoftTypography variant="button" fontWeight="medium" color={color}>
            {progress.content}
          </SoftTypography>
        </SoftBox>
      </SoftBox>
    </SoftBox>
  ));

  return (
    <Card sx={{ height: "100%" }}>
      <SoftBox padding="1rem">
        <SoftBox
          variant="gradient"
          bgColor={color}
          borderRadius="lg"
          py={2}
          pr={0.5}
          mb={3}
          height="12.5rem"
        >
          <canvas ref={chartRef} style={{ height: '100%' }} />
        </SoftBox>
        <SoftBox px={1}>
          <SoftBox mb={2}>
            <SoftTypography variant="h6" fontWeight="medium">
              {title}
            </SoftTypography>
            <SoftTypography component="div" variant="button" color="text" fontWeight="regular">
              {description}
            </SoftTypography>
          </SoftBox>
          <SoftBox py={1} px={0.5}>
            {renderItems}
          </SoftBox>
        </SoftBox>
      </SoftBox>
    </Card>
  );
};

export default ReportsBarChart; 
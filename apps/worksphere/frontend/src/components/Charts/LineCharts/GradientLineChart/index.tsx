import { FC, useRef, useEffect } from 'react';

// @mui material components
import Card from '@mui/material/Card';

// Chart.js
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
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
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface GradientLineChartProps {
  title: string;
  description?: React.ReactNode;
  height: string;
  chart: {
    labels: string[];
    datasets: Array<{
      label: string;
      color: string;
      data: number[];
    }>;
  };
}

const GradientLineChart: FC<GradientLineChartProps> = ({ title, description, height, chart }) => {
  const chartRef = useRef<HTMLCanvasElement | null>(null);
  const chartInstance = useRef<Chart | null>(null);

  useEffect(() => {
    const ctx = chartRef.current?.getContext('2d');

    if (ctx) {
      const gradientStroke = ctx.createLinearGradient(0, 230, 0, 50);
      gradientStroke.addColorStop(1, 'rgba(203,12,159,0.2)');
      gradientStroke.addColorStop(0.2, 'rgba(72,72,176,0.0)');
      gradientStroke.addColorStop(0, 'rgba(203,12,159,0)');

      const chartConfig = configs(chart.labels, chart.datasets, gradientStroke);

      // Destroy previous chart instance
      if (chartInstance.current) {
        chartInstance.current.destroy();
      }

      // Create new chart instance
      chartInstance.current = new Chart(ctx, {
        type: 'line',
        data: chartConfig.data,
        options: chartConfig.options,
      });
    }

    // Cleanup function
    return () => {
      if (chartInstance.current) {
        chartInstance.current.destroy();
      }
    };
  }, [chart]);

  return (
    <Card>
      <SoftBox padding="1rem">
        {title || description ? (
          <SoftBox px={description ? 1 : 0} pt={description ? 1 : 0}>
            {title && (
              <SoftBox mb={1}>
                <SoftTypography variant="h6">{title}</SoftTypography>
              </SoftBox>
            )}
            <SoftBox mb={2}>
              <SoftTypography component="div" variant="button" fontWeight="regular" color="text">
                {description}
              </SoftTypography>
            </SoftBox>
          </SoftBox>
        ) : null}
        <SoftBox height={height}>
          <canvas ref={chartRef} style={{ height: '100%' }} />
        </SoftBox>
      </SoftBox>
    </Card>
  );
};

export default GradientLineChart; 
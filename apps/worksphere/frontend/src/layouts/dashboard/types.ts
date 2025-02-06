import { ReactNode } from 'react';

export interface ChartData {
  labels: string[];
  datasets: {
    label: string;
    data: number[];
    [key: string]: any;
  }[];
}

export interface StatisticsCardProps {
  title: {
    text: string;
    [key: string]: any;
  };
  count: string;
  percentage: {
    color: 'success' | 'error' | 'warning' | 'info';
    text: string;
  };
  icon: {
    color: 'primary' | 'secondary' | 'info' | 'success' | 'warning' | 'error';
    component: string | ReactNode;
  };
}

export interface ReportsBarChartProps {
  title: string;
  description: ReactNode;
  chart: ChartData;
  items: {
    icon: { color: string; component: string };
    label: string;
    progress: { content: string; percentage: number };
  }[];
}

export interface GradientLineChartProps {
  title: string;
  description: ReactNode;
  height: string;
  chart: ChartData;
}

export interface ProjectsProps {
  // Add specific props if needed
}

export interface OrderOverviewProps {
  // Add specific props if needed
} 
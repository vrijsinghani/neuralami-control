import { ChartData } from '../types';

interface ReportsBarChartItem {
  icon: {
    color: string;
    component: string;
  };
  label: string;
  progress: {
    content: string;
    percentage: number;
  };
}

interface ReportsBarChartData {
  chart: ChartData;
  items: ReportsBarChartItem[];
}

const reportsBarChartData: ReportsBarChartData = {
  chart: {
    labels: ["M", "T", "W", "T", "F", "S", "S"],
    datasets: {
      label: "Sales",
      data: [50, 20, 10, 22, 50, 10, 40],
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

export default reportsBarChartData; 
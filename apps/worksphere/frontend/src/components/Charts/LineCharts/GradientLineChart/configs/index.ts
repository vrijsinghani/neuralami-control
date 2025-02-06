interface Dataset {
  label: string;
  color: string;
  data: number[];
}

function configs(labels: string[], datasets: Dataset[], gradientStroke: CanvasGradient) {
  const backgroundColors = [
    "rgba(58, 65, 111, 0.95)",
    "rgba(203, 12, 159, 0.95)",
    "rgba(0, 183, 255, 0.95)",
  ];

  return {
    data: {
      labels,
      datasets: datasets.map((dataset, index) => ({
        label: dataset.label,
        tension: 0.4,
        pointRadius: 0,
        borderColor: dataset.color,
        borderWidth: 3,
        backgroundColor: backgroundColors[index] || gradientStroke,
        fill: true,
        data: dataset.data,
        maxBarThickness: 6,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          display: false,
        },
      },
      interaction: {
        intersect: false,
        mode: "index",
      },
      scales: {
        y: {
          grid: {
            drawBorder: false,
            display: true,
            drawOnChartArea: true,
            drawTicks: false,
            borderDash: [5, 5],
            color: "rgba(255, 255, 255, .2)",
          },
          ticks: {
            display: true,
            color: "#f8f9fa",
            padding: 10,
            font: {
              size: 14,
              weight: 300,
              family: "Roboto",
              style: "normal",
              lineHeight: 2,
            },
          },
        },
        x: {
          grid: {
            drawBorder: false,
            display: false,
            drawOnChartArea: false,
            drawTicks: false,
            borderDash: [5, 5],
          },
          ticks: {
            display: true,
            color: "#f8f9fa",
            padding: 10,
            font: {
              size: 14,
              weight: 300,
              family: "Roboto",
              style: "normal",
              lineHeight: 2,
            },
          },
        },
      },
    },
  };
}

export default configs; 
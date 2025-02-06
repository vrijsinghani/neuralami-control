/**
 * Converts a color (hex or rgb) to rgba
 * @param {string} color - The color value (hex or rgb)
 * @param {number} opacity - The opacity value (0-1)
 * @returns {string} The rgba color string
 */

import { hexToRgb } from "./hexToRgb";

export function rgba(color: string, opacity: number): string {
  if (opacity < 0 || opacity > 1) {
    throw new Error("Opacity must be between 0 and 1");
  }

  // Check if the color is already in RGB format
  const isRGB = color.match(/^rgb/);
  
  if (isRGB) {
    // Extract RGB values from the string
    const [r, g, b] = color
      .replace(/[^0-9,]/g, "")
      .split(",")
      .map(val => parseInt(val.trim()));
    
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
  }

  return `rgba(${hexToRgb(color)}, ${opacity})`;
}

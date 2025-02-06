/**
 * Creates a linear gradient CSS value
 * @param {string} angle - The gradient angle (e.g., '45deg', 'to right', etc.)
 * @param {string} startColor - The starting color
 * @param {string} endColor - The ending color
 * @returns {string} The linear gradient CSS value
 */
export function linearGradient(
  angle: string,
  startColor: string,
  endColor: string
): string {
  return `linear-gradient(${angle}, ${startColor}, ${endColor})`;
}

/**
 * Converts a hex color to its RGB representation
 * @param {string} hex - The hexadecimal color string
 * @returns {string} The RGB color string
 */
export function hexToRgb(hex: string): string {
  const cleanHex = hex.startsWith("#") ? hex.slice(1) : hex;

  // Convert 3-digit hex to 6-digit
  const fullHex = cleanHex.length === 3
    ? cleanHex.split("").map(char => char + char).join("")
    : cleanHex;

  const r = parseInt(fullHex.slice(0, 2), 16);
  const g = parseInt(fullHex.slice(2, 4), 16);
  const b = parseInt(fullHex.slice(4, 6), 16);

  return `${r}, ${g}, ${b}`;
}

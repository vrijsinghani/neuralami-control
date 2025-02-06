/**
 * Converts px units to rem
 * @param {number} number - The value in pixels
 * @returns {string} The value in rem
 */
export function pxToRem(number: number): string {
  return `${number / 16}rem`;
}

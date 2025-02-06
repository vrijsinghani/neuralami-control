/**
 * Generates a box shadow CSS value
 */
export function boxShadow(
  offset: [number, number],
  radius: [number, number],
  color: string,
  opacity: number,
  inset: string = ""
): string {
  const [x, y] = offset;
  const [blur, spread] = radius;

  return `${inset} ${x}px ${y}px ${blur}px ${spread}px ${color}`;
}

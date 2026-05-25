let counter = 0

export function nextMockId(prefix: string): string {
  counter += 1
  return `${prefix}-${Date.now()}-${counter}`
}

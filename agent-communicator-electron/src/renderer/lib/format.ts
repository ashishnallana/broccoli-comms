import type { AgentStatus, RuntimeHealth } from '../../shared/contracts'

export function statusGlyph(status: AgentStatus): string {
  switch (status) {
    case 'idle':
      return '●'
    case 'busy':
      return '●'
    case 'waiting':
      return '●'
    case 'offline':
      return '●'
  }
}

export function healthLabel(health: RuntimeHealth): string {
  if (health === 'healthy') return 'healthy'
  if (health === 'degraded') return 'degraded'
  return 'offline'
}

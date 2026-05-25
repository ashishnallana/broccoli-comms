import type { CommunicatorRuntimeClient } from '../../../shared/contracts'
import { MockRuntimeClient } from './mockRuntime'

export function createRuntimeClient(): CommunicatorRuntimeClient {
  if (window.broccoliCommsMock) {
    return window.broccoliCommsMock
  }
  return new MockRuntimeClient()
}

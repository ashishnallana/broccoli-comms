/// <reference types="vite/client" />

import type { BroccoliCommsMockApi } from '../main/preload'

declare global {
  interface Window {
    broccoliCommsMock?: BroccoliCommsMockApi
  }
}

export {}

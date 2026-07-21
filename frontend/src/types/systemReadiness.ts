export type ReadinessStatus = 'ready' | 'degraded' | 'blocked'
export type ReadinessCheckStatus = 'pass' | 'warn' | 'fail'

export interface ReadinessCheck {
  id: string
  label: string
  status: ReadinessCheckStatus
  required: boolean
  message: string
  details: Record<string, unknown>
}

export interface ReadinessCapabilities {
  projectEditing: boolean
  voiceover: boolean
  previewRendering: boolean
  jianyingZipExport: boolean
  jianyingDirectExport: boolean
}

export interface SystemReadinessResponse {
  status: ReadinessStatus
  checkedAt: string
  app: { name: string; version: string; productionMode: boolean }
  checks: ReadinessCheck[]
  capabilities: ReadinessCapabilities
  summary: { passed: number; warnings: number; failed: number }
}

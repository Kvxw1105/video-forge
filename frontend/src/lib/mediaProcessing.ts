export type MediaCapability = 'media.probe' | 'video.trim' | 'audio.extract'

export type MediaProbeResult = {
  format_meta?: {
    container?: string | null
    bitrate?: number | null
    duration?: number | null
    size?: number | null
  }
  video_stream_meta?: {
    codec?: string | null
    bitrate?: number | null
    duration?: number | null
    fps?: number | null
    width?: number | null
    height?: number | null
    dynamic_range?: string | null
  }
  audio_stream_meta?: {
    codec?: string | null
    bitrate?: number | null
    duration?: number | null
    sample_rate?: number | null
    channels?: number | null
  }
}

export type MediaExecution = {
  id: string
  status: 'submitted' | 'waiting' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  capability: MediaCapability
  sourceAssetId?: string | null
  outputPath?: string | null
  artifactId?: string | null
  result?: MediaProbeResult & Record<string, unknown>
  providerError?: { message?: string; [key: string]: unknown } | null
}

export type MediaExecutionResponse = {
  execution: MediaExecution
  recordPath: string
}

export function requireSucceeded(response: MediaExecutionResponse): MediaExecution {
  if (response.execution.status !== 'succeeded') {
    throw new Error(response.execution.providerError?.message || '素材处理失败')
  }
  return response.execution
}

export function formatDuration(value?: number | null): string {
  if (!Number.isFinite(value) || Number(value) < 0) return '--'
  const total = Number(value)
  const minutes = Math.floor(total / 60)
  const seconds = total - minutes * 60
  return minutes > 0 ? `${minutes}:${seconds.toFixed(1).padStart(4, '0')}` : `${seconds.toFixed(1)} 秒`
}

export function formatBytes(value?: number | null): string {
  if (!Number.isFinite(value) || Number(value) < 0) return '--'
  const bytes = Number(value)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

export function mediaStreamUrl(projectId: string, path: string): string {
  return `/api/projects/${encodeURIComponent(projectId)}/assets/stream?path=${encodeURIComponent(path)}`
}

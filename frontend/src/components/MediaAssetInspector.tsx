import { useEffect, useMemo, useRef, useState } from 'react'
import { CheckCircle, Info, Scissors, Spinner, Warning, Waveform, X } from '@phosphor-icons/react'

import { api } from '../lib/api'
import {
  formatBytes,
  formatDuration,
  mediaStreamUrl,
  requireSucceeded,
  type MediaExecution,
  type MediaProbeResult,
} from '../lib/mediaProcessing'

type ProjectAsset = {
  id?: string
  name?: string
  path: string
  metadata?: Record<string, unknown>
}

type Props = {
  projectId: string
  asset: ProjectAsset
  onProjectRefresh: () => Promise<void>
}

type Task = 'probe' | 'trim' | 'extract' | null

export default function MediaAssetInspector({ projectId, asset, onProjectRefresh }: Props) {
  const [available, setAvailable] = useState<boolean | null>(null)
  const [probe, setProbe] = useState<MediaProbeResult | null>(null)
  const [task, setTask] = useState<Task>(null)
  const [error, setError] = useState('')
  const [result, setResult] = useState<MediaExecution | null>(null)
  const [showTrim, setShowTrim] = useState(false)
  const [startTime, setStartTime] = useState('0')
  const [endTime, setEndTime] = useState('')
  const probeCache = useRef(new Map<string, MediaProbeResult>())

  const assetKey = asset.id || asset.path
  const duration = Number(probe?.format_meta?.duration ?? probe?.video_stream_meta?.duration ?? 0)
  const video = probe?.video_stream_meta
  const audio = probe?.audio_stream_meta
  const canRun = available === true && Boolean(asset.id) && task === null

  useEffect(() => {
    let active = true
    api.getMediaProviders()
      .then((payload) => {
        const provider = payload.providers?.find((item: any) => item.provider === payload.default)
        if (active) setAvailable(Boolean(provider?.installed))
      })
      .catch(() => { if (active) setAvailable(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    setError('')
    setResult(null)
    const cached = probeCache.current.get(assetKey)
    if (cached) {
      setProbe(cached)
      return
    }
    setProbe(null)
    if (available !== true || !asset.id) return

    let active = true
    setTask('probe')
    api.executeMedia(projectId, {
      capability: 'media.probe',
      sourceAssetId: asset.id,
      idempotencyToken: `asset-inspector-${asset.id}`,
    })
      .then((response) => {
        const execution = requireSucceeded(response)
        const facts = execution.result || {}
        probeCache.current.set(assetKey, facts)
        if (active) setProbe(facts)
      })
      .catch((reason) => { if (active) setError(reason.message || '读取素材信息失败') })
      .finally(() => { if (active) setTask(null) })
    return () => { active = false }
  }, [asset.id, assetKey, available, projectId])

  useEffect(() => {
    if (duration > 0) setEndTime(duration.toFixed(1))
  }, [duration, assetKey])

  const facts = useMemo(() => [
    { label: '时长', value: formatDuration(duration || null) },
    { label: '画面', value: video?.width && video?.height ? `${video.width} x ${video.height}` : '--' },
    { label: '帧率', value: video?.fps ? `${Number(video.fps).toFixed(2)} fps` : '--' },
    { label: '编码', value: video?.codec?.toUpperCase() || '--' },
    { label: '大小', value: formatBytes(probe?.format_meta?.size) },
    { label: '音轨', value: audio ? `${audio.codec?.toUpperCase() || '音频'} · ${audio.channels || '--'} 声道` : '无' },
  ], [audio, duration, probe?.format_meta?.size, video])

  const runExtract = async () => {
    if (!asset.id || !canRun) return
    setTask('extract')
    setError('')
    setResult(null)
    try {
      const execution = requireSucceeded(await api.executeMedia(projectId, {
        capability: 'audio.extract',
        sourceAssetId: asset.id,
        idempotencyToken: `asset-extract-${asset.id}-${Date.now()}`,
      }))
      setResult(execution)
      await onProjectRefresh()
    } catch (reason: any) {
      setError(reason.message || '音频提取失败')
    } finally {
      setTask(null)
    }
  }

  const runTrim = async () => {
    if (!asset.id || !canRun) return
    const start = Number(startTime)
    const end = Number(endTime)
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end <= start || (duration > 0 && end > duration + 0.05)) {
      setError(`请输入有效区间${duration > 0 ? `，结束时间不超过 ${duration.toFixed(1)} 秒` : ''}`)
      return
    }
    setTask('trim')
    setError('')
    setResult(null)
    try {
      const execution = requireSucceeded(await api.executeMedia(projectId, {
        capability: 'video.trim',
        sourceAssetId: asset.id,
        startTime: start,
        endTime: end,
        idempotencyToken: `asset-trim-${asset.id}-${Date.now()}`,
      }))
      setResult(execution)
      setShowTrim(false)
      await onProjectRefresh()
    } catch (reason: any) {
      setError(reason.message || '视频裁剪失败')
    } finally {
      setTask(null)
    }
  }

  return (
    <div className="mt-3 border-t pt-3" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <Info size={13} weight="bold" style={{ color: 'var(--accent)' }} />
            <h4 className="text-[11px] font-semibold" style={{ color: 'var(--text-primary)' }}>素材处理</h4>
          </div>
          <p className="text-[10px] truncate mt-0.5" style={{ color: 'var(--text-muted)' }}>{asset.name || asset.path.split(/[\\/]/).pop()}</p>
        </div>
        {task === 'probe' && <span className="text-[10px] flex items-center gap-1" style={{ color: 'var(--text-muted)' }}><Spinner size={11} className="animate-spin" />读取中</span>}
      </div>

      {available === false ? (
        <div className="flex items-start gap-2 rounded-md px-2.5 py-2 text-[10px]" style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
          <Warning size={13} className="shrink-0 mt-0.5" />
          本地媒体能力未就绪，请检查 FFmpeg 安装。
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-x-2 gap-y-2 py-2.5">
            {facts.map((fact) => (
              <div key={fact.label} className="min-w-0">
                <div className="text-[9px]" style={{ color: 'var(--text-muted)' }}>{fact.label}</div>
                <div className="text-[10px] font-mono truncate mt-0.5" style={{ color: 'var(--text-primary)' }} title={fact.value}>{fact.value}</div>
              </div>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => { setError(''); setShowTrim(true) }}
              disabled={!canRun || !probe}
              className="btn-cinematic min-h-9 text-[11px] flex items-center justify-center gap-1.5 disabled:opacity-45"
            >
              {task === 'trim' ? <Spinner size={13} className="animate-spin" /> : <Scissors size={13} weight="bold" />}
              裁剪片段
            </button>
            <button
              type="button"
              onClick={runExtract}
              disabled={!canRun || !probe || !audio}
              className="btn-cinematic min-h-9 text-[11px] flex items-center justify-center gap-1.5 disabled:opacity-45"
              title={!audio && probe ? '这个视频没有音轨' : '提取为可复用的 MP3 素材'}
            >
              {task === 'extract' ? <Spinner size={13} className="animate-spin" /> : <Waveform size={13} weight="bold" />}
              {task === 'extract' ? '提取中' : '提取音频'}
            </button>
          </div>
        </>
      )}

      {error && (
        <div role="alert" className="mt-2 flex items-start gap-1.5 text-[10px] rounded-md px-2.5 py-2" style={{ color: 'var(--danger)', background: 'var(--bg-surface)', border: '1px solid var(--danger)' }}>
          <Warning size={12} className="shrink-0 mt-0.5" />{error}
        </div>
      )}

      {result?.outputPath && (
        <div className="mt-2 rounded-md overflow-hidden" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          <div className="flex items-center gap-1.5 px-2.5 py-2 text-[10px]" style={{ color: 'var(--text-primary)' }}>
            <CheckCircle size={13} weight="fill" style={{ color: 'var(--success)' }} />
            已生成并加入项目素材
          </div>
          {result.capability === 'audio.extract' ? (
            <audio controls className="w-full h-9 px-2 pb-2" src={mediaStreamUrl(projectId, result.outputPath)} />
          ) : (
            <video controls className="w-full aspect-video object-contain" style={{ background: 'var(--bg-base)' }} src={mediaStreamUrl(projectId, result.outputPath)} />
          )}
        </div>
      )}

      {showTrim && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" style={{ background: 'rgba(0,0,0,0.46)' }} onClick={() => task === null && setShowTrim(false)}>
          <div role="dialog" aria-modal="true" aria-labelledby="trim-title" className="glass-panel w-full max-w-sm rounded-lg shadow-lg overflow-hidden" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
              <div>
                <h3 id="trim-title" className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>裁剪为新素材</h3>
                <p className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>原素材保持不变，结果加入当前项目</p>
              </div>
              <button type="button" className="icon-button" title="关闭" aria-label="关闭裁剪" disabled={task !== null} onClick={() => setShowTrim(false)}><X size={15} /></button>
            </div>
            <div className="p-4">
              <div className="grid grid-cols-2 gap-3">
                <label className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                  开始时间（秒）
                  <input autoFocus type="number" min="0" step="0.1" value={startTime} onChange={(event) => setStartTime(event.target.value)} className="input-cinematic w-full mt-1 font-mono" />
                </label>
                <label className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                  结束时间（秒）
                  <input type="number" min="0.1" max={duration || undefined} step="0.1" value={endTime} onChange={(event) => setEndTime(event.target.value)} className="input-cinematic w-full mt-1 font-mono" />
                </label>
              </div>
              <div className="flex items-center justify-between mt-2 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                <span>源时长 {formatDuration(duration || null)}</span>
                <span>片段 {formatDuration(Math.max(0, Number(endTime) - Number(startTime)))}</span>
              </div>
              <button type="button" onClick={runTrim} disabled={task !== null} className="btn-gold w-full min-h-10 mt-4 text-xs flex items-center justify-center gap-2 disabled:opacity-45">
                {task === 'trim' ? <Spinner size={14} className="animate-spin" /> : <Scissors size={14} weight="bold" />}
                {task === 'trim' ? '正在生成片段' : '生成新片段'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

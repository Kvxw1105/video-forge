import { useState, useRef, useEffect } from 'react'
import { MusicNote, Microphone, UploadSimple, Play, Pause, Trash, Plus, ListNumbers } from '@phosphor-icons/react'
import { api } from '../../lib/api'
import { useProgress, LoadingProgress } from '../../hooks/useProgress'

interface BGMTrack {
  file: string
  volume: number
  trimStart: number
  trimEnd: number
  startAt?: number
  fadeIn: number
  fadeOut: number
}

interface SFXTrack {
  file: string
  startAt: number
  volume: number
  trimStart?: number
  trimEnd?: number
}

export default function AudioPanel({
  projectId, bgmTracks, sfxTracks = [], voiceoverVolume, voiceoverUrl,
  onBgmTracksChange, onSfxTracksChange, onVoiceoverVolumeChange, onError,
  cueMode, onCueModeChange,
}: {
  projectId: string
  bgmTracks: BGMTrack[]
  sfxTracks?: SFXTrack[]
  voiceoverVolume: number
  voiceoverUrl: string
  onBgmTracksChange: (tracks: BGMTrack[]) => void
  onSfxTracksChange?: (tracks: SFXTrack[]) => void
  onVoiceoverVolumeChange: (v: number) => void
  onError?: (msg: string) => void
  cueMode?: string
  onCueModeChange?: (mode: string) => void
}) {
  const [uploading, setUploading] = useState(false)
  const uploadProgress = useProgress()
  const [voPlaying, setVoPlaying] = useState(false)
  const [localVoVol, setLocalVoVol] = useState(voiceoverVolume)
  const [expandedTrack, setExpandedTrack] = useState<number | null>(bgmTracks.length > 0 ? 0 : null)
  const [bgmPlayIdx, setBgmPlayIdx] = useState<number | null>(null)
  const bgmAudioRef = useRef<HTMLAudioElement>(null)
  const voAudioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => { setLocalVoVol(voiceoverVolume) }, [voiceoverVolume])
  useEffect(() => {
    if (voAudioRef.current) voAudioRef.current.volume = Math.min(Math.max(localVoVol, 0), 1)
  }, [localVoVol])

  const toggleVo = () => {
    const el = voAudioRef.current
    if (!el || !voiceoverUrl) return
    if (voPlaying) { el.pause(); setVoPlaying(false) }
    else { el.play(); setVoPlaying(true) }
  }

  useEffect(() => { setVoPlaying(false) }, [voiceoverUrl])

  const toggleBgm = (idx: number) => {
    const el = bgmAudioRef.current
    if (!el) return
    const track = bgmTracks[idx]
    if (!track) return
    if (bgmPlayIdx === idx) {
      el.pause(); setBgmPlayIdx(null)
    } else {
      const url = `/api/projects/${projectId}/assets/stream?path=${encodeURIComponent(track.file)}`
      el.src = url
      el.volume = Math.min(Math.max(track.volume, 0), 1)
      el.currentTime = track.trimStart || 0  // Start from trim position
      el.play().catch(() => {})  // Suppress autoplay error
      setBgmPlayIdx(idx)
    }
  }

  // Update playing BGM volume when slider changes
  useEffect(() => {
    if (bgmPlayIdx !== null && bgmAudioRef.current) {
      const track = bgmTracks[bgmPlayIdx]
      if (track) bgmAudioRef.current.volume = Math.min(Math.max(track.volume, 0), 1)
    }
  }, [bgmTracks, bgmPlayIdx])

  // Check trimEnd during BGM playback — pause when reaching trimEnd
  useEffect(() => {
    const el = bgmAudioRef.current
    if (!el || bgmPlayIdx === null) return
    const track = bgmTracks[bgmPlayIdx]
    if (!track) return
    const checkTrim = () => {
      if (track.trimEnd > 0 && el.currentTime >= track.trimEnd) {
        el.pause(); setBgmPlayIdx(null)
      }
    }
    el.addEventListener('timeupdate', checkTrim)
    return () => el.removeEventListener('timeupdate', checkTrim)
  }, [bgmPlayIdx, bgmTracks])

  useEffect(() => { if (bgmAudioRef.current) bgmAudioRef.current.pause(); setBgmPlayIdx(null) }, [bgmTracks])

  const handleAddBgm = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    uploadProgress.start('上传 BGM...')
    try {
      const r = await api.uploadAsset(projectId, file)
      const newTrack: BGMTrack = {
        file: r.path, volume: 0.3, trimStart: 0, trimEnd: 0, startAt: 0, fadeIn: 0, fadeOut: 0,
      }
      onBgmTracksChange([...bgmTracks, newTrack])
      uploadProgress.finish('BGM 已上传')
    } catch (err) {
      uploadProgress.fail('BGM 上传失败')
      onError?.('BGM 上传失败')
    } finally {
      setUploading(false)
    }
  }

  const handleAddSfx = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    uploadProgress.start('上传音效...')
    try {
      const r = await api.uploadAsset(projectId, file)
      onSfxTracksChange?.([...sfxTracks, { file: r.path, startAt: 0, volume: 0.8, trimStart: 0, trimEnd: 0 }])
      uploadProgress.finish('音效已上传')
    } catch {
      uploadProgress.fail('音效上传失败')
      onError?.('音效上传失败')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const updateSfx = (idx: number, patch: Partial<SFXTrack>) => {
    onSfxTracksChange?.(sfxTracks.map((t, i) => i === idx ? { ...t, ...patch } : t))
  }

  const removeSfx = (idx: number) => {
    onSfxTracksChange?.(sfxTracks.filter((_, i) => i !== idx))
  }

  const updateTrack = (idx: number, patch: Partial<BGMTrack>) => {
    const updated = bgmTracks.map((t, i) => i === idx ? { ...t, ...patch } : t)
    onBgmTracksChange(updated)
  }

  const removeTrack = (idx: number) => {
    onBgmTracksChange(bgmTracks.filter((_, i) => i !== idx))
  }

  const CUE_MODES = [
    { key: 'beat', label: '节拍卡点', desc: '每拍切一张' },
    { key: 'onset', label: '重音卡点', desc: '每个重音切' },
    { key: 'energy', label: '能量卡点', desc: '高能段密集' },
    { key: 'uniform', label: '均匀分布', desc: '等间隔' },
  ]

  return (
    <section className="panel-section space-y-4">
      <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-primary)' }}>音频</h3>
      <LoadingProgress active={uploadProgress.active} progress={uploadProgress.progress} label={uploadProgress.label} failed={uploadProgress.failed} />

      {/* 配音 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium flex items-center gap-1.5" style={{ color: 'var(--text-primary)' }}>
            <Microphone size={14} weight="bold" /> 配音
          </span>
        </div>
        {voiceoverUrl ? (
          <>
            <audio key={voiceoverUrl} ref={voAudioRef} src={voiceoverUrl} preload="metadata" onEnded={() => setVoPlaying(false)} />
            <audio ref={bgmAudioRef} preload="metadata" onEnded={() => setBgmPlayIdx(null)} />
            <div className="flex items-center gap-2 mb-2">
            <button onClick={toggleVo}
                className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-all active:scale-90"
                style={{ background: 'var(--accent)', color: 'var(--accent-contrast)' }}
              >
                {voPlaying ? <Pause size={14} weight="fill" /> : <Play size={14} weight="fill" />}
              </button>
              <p className="text-xs truncate" style={{ color: 'var(--text-muted)' }}>AI 生成的配音</p>
            </div>
          </>
        ) : (
          <p className="text-xs italic mb-2" style={{ color: 'var(--text-muted)' }}>尚未生成配音</p>
        )}
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium w-8" style={{ color: 'var(--text-muted)' }}>音量</span>
          <input
            type="range" min="0" max="2" step="0.01"
            value={localVoVol}
            onChange={(e) => {
              const next = Number(e.target.value)
              setLocalVoVol(next)
              onVoiceoverVolumeChange(next)
            }}
            onMouseUp={() => onVoiceoverVolumeChange(localVoVol)}
            onKeyUp={(e) => {
              if (e.key === 'ArrowUp' || e.key === 'ArrowDown') onVoiceoverVolumeChange(localVoVol)
            }}
            disabled={!voiceoverUrl}
            className="flex-1 accent-[var(--accent)] h-1.5 disabled:opacity-50"
          />
          <span className="text-xs font-semibold w-10 text-right tabular-nums" style={{ color: 'var(--text-primary)' }}>{Math.round(localVoVol * 100)}%</span>
        </div>
      </div>

      {/* BGM 轨道列表 */}
      <div className="pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium flex items-center gap-1.5" style={{ color: 'var(--text-primary)' }}>
            <MusicNote size={14} weight="bold" /> 背景音乐
          </span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{bgmTracks.length} 首</span>
        </div>

        {bgmTracks.map((track, idx) => (
          <div key={idx} className="mb-2 rounded-lg p-2.5" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono w-4" style={{ color: 'var(--text-muted)' }}>#{idx + 1}</span>
              <button onClick={() => toggleBgm(idx)}
                className="w-6 h-6 rounded-full flex items-center justify-center shrink-0 transition-all active:scale-90"
                style={{ background: bgmPlayIdx === idx ? 'var(--accent)' : 'var(--bg-surface)', color: bgmPlayIdx === idx ? 'var(--accent-contrast)' : 'var(--text-muted)', border: '1px solid var(--border)' }}
              >
                {bgmPlayIdx === idx ? <Pause size={10} weight="fill" /> : <Play size={10} weight="fill" />}
              </button>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>{track.file.split(/[\\/]/).pop()}</p>
                {/* Volume slider always visible */}
                <div className="flex items-center gap-1 mt-1">
                  <input
                    type="range" min="0" max="1" step="0.05"
                    value={track.volume}
                    onChange={(e) => updateTrack(idx, { volume: Number(e.target.value) })}
                    className="flex-1 h-1 accent-[var(--accent)]"
                  />
                  <span className="text-[9px] font-mono w-6 text-right" style={{ color: 'var(--text-muted)' }}>{Math.round(track.volume * 100)}%</span>
                </div>
              </div>
              <button
                onClick={() => setExpandedTrack(expandedTrack === idx ? null : idx)}
                className="text-[10px] transition-colors hover:opacity-80"
                style={{ color: 'var(--text-muted)' }}
              >
                {expandedTrack === idx ? '收起' : '裁剪'}
              </button>
              <button
                onClick={() => removeTrack(idx)}
                className="w-6 h-6 rounded hover:text-red-500 hover:bg-red-50 flex items-center justify-center transition-all"
                style={{ color: 'var(--text-muted)' }}
              >
                <Trash size={12} weight="bold" />
              </button>
            </div>

            {/* 展开的裁剪控制 */}
            {expandedTrack === idx && (
              <div className="mt-2 space-y-2">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] w-12" style={{ color: 'var(--text-muted)' }}>入场</span>
                  <input
                    type="number" min="0" step="0.1"
                    value={track.startAt || 0}
                    onChange={(e) => updateTrack(idx, { startAt: Number(e.target.value) })}
                    className="flex-1 rounded px-2 py-0.5 text-[11px] font-mono" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                  />
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>视频秒</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] w-12" style={{ color: 'var(--text-muted)' }}>裁剪起</span>
                  <input
                    type="number" min="0" step="0.1"
                    value={track.trimStart}
                    onChange={(e) => updateTrack(idx, { trimStart: Number(e.target.value) })}
                    className="flex-1 rounded px-2 py-0.5 text-[11px] font-mono" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                  />
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>音乐秒</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] w-12" style={{ color: 'var(--text-muted)' }}>裁剪止</span>
                  <input
                    type="number" min="0" step="0.1"
                    value={track.trimEnd}
                    onChange={(e) => updateTrack(idx, { trimEnd: Number(e.target.value) })}
                    className="flex-1 rounded px-2 py-0.5 text-[11px] font-mono" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                  />
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>秒 (0=不限)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] w-12" style={{ color: 'var(--text-muted)' }}>淡入</span>
                  <input
                    type="range" min="0" max="5" step="0.1"
                    value={track.fadeIn}
                    onChange={(e) => updateTrack(idx, { fadeIn: Number(e.target.value) })}
                    className="flex-1 accent-[var(--accent)] h-1"
                  />
                  <span className="text-[10px] w-8" style={{ color: 'var(--text-muted)' }}>{track.fadeIn}s</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] w-12" style={{ color: 'var(--text-muted)' }}>淡出</span>
                  <input
                    type="range" min="0" max="5" step="0.1"
                    value={track.fadeOut}
                    onChange={(e) => updateTrack(idx, { fadeOut: Number(e.target.value) })}
                    className="flex-1 accent-[var(--accent)] h-1"
                  />
                  <span className="text-[10px] w-8" style={{ color: 'var(--text-muted)' }}>{track.fadeOut}s</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] w-12" style={{ color: 'var(--text-muted)' }}>音量</span>
                  <input
                    type="range" min="0" max="1" step="0.01"
                    value={track.volume}
                    onChange={(e) => updateTrack(idx, { volume: Number(e.target.value) })}
                    className="flex-1 accent-[var(--accent)] h-1"
                  />
                  <span className="text-[10px] w-8" style={{ color: 'var(--text-muted)' }}>{Math.round(track.volume * 100)}%</span>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* 添加 BGM */}
        <label className="flex items-center gap-2 cursor-pointer group mt-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors" style={{ background: 'var(--bg-elevated)' }}>
            <Plus size={14} style={{ color: 'var(--text-muted)' }} />
          </div>
          <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{uploading ? '上传中...' : '添加 BGM'}</span>
          <input type="file" accept="audio/*" onChange={handleAddBgm} className="hidden" disabled={uploading} />
        </label>
      </div>

      {/* 音效轨道 */}
      <div className="pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>音效</span>
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{sfxTracks.length} 个</span>
        </div>
        {sfxTracks.map((track, idx) => (
          <div key={idx} className="mb-2 rounded-lg p-2.5 space-y-2" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>#{idx + 1}</span>
              <p className="text-xs font-medium truncate flex-1" style={{ color: 'var(--text-primary)' }}>{track.file.split(/[\\/]/).pop()}</p>
              <button onClick={() => removeSfx(idx)} className="w-6 h-6 rounded flex items-center justify-center" style={{ color: 'var(--text-muted)' }}><Trash size={12} /></button>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>出现秒
                <input type="number" min="0" step="0.1" value={track.startAt} onChange={(e) => updateSfx(idx, { startAt: Number(e.target.value) })}
                  className="w-full rounded px-2 py-0.5 text-[11px] font-mono mt-1" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
              </label>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>音量 {Math.round(track.volume * 100)}%
                <input type="range" min="0" max="1" step="0.05" value={track.volume} onChange={(e) => updateSfx(idx, { volume: Number(e.target.value) })}
                  className="w-full h-1 accent-[var(--accent)] mt-2" />
              </label>
            </div>
          </div>
        ))}
        <label className="flex items-center gap-2 cursor-pointer group mt-2">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center transition-colors" style={{ background: 'var(--bg-elevated)' }}>
            <Plus size={14} style={{ color: 'var(--text-muted)' }} />
          </div>
          <span className="text-xs font-medium" style={{ color: 'var(--text-secondary)' }}>{uploading ? '上传中...' : '添加音效'}</span>
          <input type="file" accept="audio/*" onChange={handleAddSfx} className="hidden" disabled={uploading} />
        </label>
      </div>

      {/* 卡点模式 */}
      <div className="pt-3 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center gap-1.5 mb-2">
          <ListNumbers size={14} weight="bold" style={{ color: 'var(--text-primary)' }} />
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>卡点模式</span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          {CUE_MODES.map(m => (
            <button
              key={m.key}
              onClick={() => onCueModeChange?.(m.key)}
              className={`text-left px-2.5 py-1.5 rounded-lg border text-[11px] transition-all ${
                cueMode === m.key ? 'selected-surface' : 'hover:opacity-90'
              }`}
              style={cueMode === m.key
                ? undefined
                : { background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border)' }
              }
            >
              <span className="font-medium">{m.label}</span>
              <span className="block text-[10px] opacity-60">{m.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}

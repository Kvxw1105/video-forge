import { useEffect, useState } from 'react'
import { Plus, Trash } from '@phosphor-icons/react'

type TimelineBlock = {
  type: 'black' | 'assets'
  duration: number | 'rest'
  source?: 'all' | 'images' | 'videos'
  mode?: 'random' | 'ordered'
  perAssetDuration?: number
  bgColor?: string
}

type Timeline = { voiceoverStartAt?: number; blocks?: TimelineBlock[] }

function parseDurationInput(value: string): number | 'rest' | null {
  const trimmed = value.trim()
  if (trimmed.toLowerCase() === 'rest') return 'rest'
  const n = Number(trimmed)
  return Number.isFinite(n) ? n : null
}

export default function RhythmPanel({
  timeline,
  onTimelineChange,
}: {
  timeline: Timeline
  onTimelineChange: (timeline: { voiceoverStartAt: number; blocks: TimelineBlock[] }) => void
}) {
  const blocks = timeline.blocks?.length ? timeline.blocks : [
    { type: 'assets' as const, duration: 'rest' as const, source: 'all' as const, mode: 'random' as const, perAssetDuration: 1 },
  ]
  const voiceoverStartAt = timeline.voiceoverStartAt || 0
  const [durationInputs, setDurationInputs] = useState<Record<number, string>>({})

  useEffect(() => {
    const next: Record<number, string> = {}
    blocks.forEach((block, idx) => { next[idx] = String(block.duration) })
    setDurationInputs(next)
  }, [JSON.stringify(blocks.map((block) => block.duration))])

  const update = (patch: Partial<{ voiceoverStartAt: number; blocks: TimelineBlock[] }>) => {
    onTimelineChange({ voiceoverStartAt, blocks, ...patch })
  }
  const updateBlock = (idx: number, patch: Partial<TimelineBlock>) => {
    update({ blocks: blocks.map((b, i) => i === idx ? { ...b, ...patch } : b) })
  }
  const updateBlockDuration = (idx: number, value: string) => {
    setDurationInputs((prev) => ({ ...prev, [idx]: value }))
    const parsed = parseDurationInput(value)
    if (parsed !== null) updateBlock(idx, { duration: parsed })
  }
  const addBlock = (block: TimelineBlock) => update({ blocks: [...blocks, block] })
  const removeBlock = (idx: number) => update({ blocks: blocks.filter((_, i) => i !== idx) })

  const fieldStyle = { color: 'var(--text-muted)' }

  return (
    <section className="panel-section space-y-3">
      <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-primary)' }}>节奏</h3>

      <div className="rounded-lg p-3 space-y-2" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
        <label className="block text-[11px] font-medium" style={{ color: 'var(--text-secondary)' }}>配音 / 字幕延后开始</label>
        <div className="flex items-center gap-2">
          <input type="number" min="0" step="0.1" value={voiceoverStartAt}
            onChange={(e) => update({ voiceoverStartAt: Number(e.target.value) })}
            className="input-cinematic text-xs flex-1" />
          <span className="text-[11px]" style={fieldStyle}>秒</span>
        </div>
        <p className="text-[10px] leading-relaxed" style={fieldStyle}>黑屏静默片头：片头几秒，这里就填几秒。</p>
      </div>

      <div className="space-y-2">
        {blocks.map((b, idx) => (
          <div key={idx} className="rounded-lg p-3 space-y-3" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded" style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>#{idx + 1}</span>
              <select value={b.type} onChange={(e) => updateBlock(idx, { type: e.target.value as TimelineBlock['type'] })} className="input-cinematic text-xs flex-1 min-w-0">
                <option value="assets">素材混剪</option>
                <option value="black">黑屏</option>
              </select>
              <button onClick={() => removeBlock(idx)} className="w-8 h-8 rounded flex items-center justify-center shrink-0" style={{ color: 'var(--text-muted)', background: 'var(--bg-surface)' }}><Trash size={13} /></button>
            </div>

            <div className="grid grid-cols-1 gap-2">
              <label className="block text-[10px]" style={fieldStyle}>时长（秒；填 rest 表示剩余时长）
                <input type="text" value={durationInputs[idx] ?? String(b.duration)} placeholder="rest"
                  onChange={(e) => updateBlockDuration(idx, e.target.value)}
                  className="input-cinematic text-xs w-full mt-1" />
              </label>
              {b.type === 'black' ? (
                <label className="block text-[10px]" style={fieldStyle}>黑屏颜色
                  <input type="color" value={b.bgColor || '#000000'} onChange={(e) => updateBlock(idx, { bgColor: e.target.value })}
                    className="w-full h-9 rounded mt-1" />
                </label>
              ) : (
                <label className="block text-[10px]" style={fieldStyle}>素材来源
                  <select value={b.source || 'all'} onChange={(e) => updateBlock(idx, { source: e.target.value as TimelineBlock['source'] })} className="input-cinematic text-xs w-full mt-1">
                    <option value="all">全部素材</option>
                    <option value="videos">只用视频</option>
                    <option value="images">只用图片</option>
                  </select>
                </label>
              )}
            </div>

            {b.type === 'assets' && (
              <div className="grid grid-cols-1 gap-2">
                <label className="block text-[10px]" style={fieldStyle}>排列模式
                  <select value={b.mode || 'random'} onChange={(e) => updateBlock(idx, { mode: e.target.value as TimelineBlock['mode'] })} className="input-cinematic text-xs w-full mt-1">
                    <option value="random">随机</option>
                    <option value="ordered">顺序</option>
                  </select>
                </label>
                <label className="block text-[10px]" style={fieldStyle}>每段素材时长（秒）
                  <input type="number" min="0.1" step="0.1" value={b.perAssetDuration || 1}
                    onChange={(e) => updateBlock(idx, { perAssetDuration: Number(e.target.value) })}
                    className="input-cinematic text-xs w-full mt-1" />
                </label>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-2">
        <button onClick={() => addBlock({ type: 'black', duration: 1.5, bgColor: '#000000' })} className="btn-cinematic text-xs py-2 flex items-center justify-center gap-1"><Plus size={12} />黑屏</button>
        <button onClick={() => addBlock({ type: 'assets', duration: 'rest', source: 'all', mode: 'random', perAssetDuration: 1 })} className="btn-cinematic text-xs py-2 flex items-center justify-center gap-1"><Plus size={12} />素材段</button>
      </div>
    </section>
  )
}

import { useState, useEffect } from 'react'
import { FrameCorners, ArrowsOutSimple, ArrowsInSimple } from '@phosphor-icons/react'

export function RatioGroup({ ratios, value, onChange }: { ratios: { key: string; label: string }[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex items-center gap-1.5">
      <FrameCorners size={16} style={{ color: 'var(--text-muted)' }} />
      {ratios.map((r) => (
        <button
          key={r.key}
          title={r.label}
          onClick={() => onChange(r.key)}
          className={`text-[11px] px-2.5 py-1.5 rounded-md font-semibold transition-all whitespace-nowrap border ${
            value === r.key ? 'selected-surface' : 'hover:opacity-90'
          }`}
          style={value === r.key
            ? undefined
            : { background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border)' }
          }
        >
          {r.key}
        </button>
      ))}
    </div>
  )
}

export function ScaleControl({ scale, onChange, disabled }: { scale: number; onChange: (v: number) => void; disabled?: boolean }) {
  const [local, setLocal] = useState(scale * 100)
  useEffect(() => setLocal(scale * 100), [scale])
  return (
    <div className="flex items-center gap-2 min-w-0">
      <ArrowsOutSimple size={14} className="shrink-0" style={{ color: 'var(--text-muted)' }} />
      <input
        type="range"
        name="previewScale"
        aria-label="画布缩放"
        min={30}
        max={200}
        step={5}
        disabled={disabled}
        value={local}
        onChange={(e) => setLocal(parseInt(e.target.value))}
        onMouseUp={() => onChange(local / 100)}
        onKeyUp={(e) => (e.key === 'ArrowUp' || e.key === 'ArrowDown') && onChange(local / 100)}
        className="w-24 disabled:opacity-40" style={{ accentColor: 'var(--accent)' }}
      />
      <span className="text-xs font-semibold w-9 text-right tabular-nums shrink-0" style={{ color: 'var(--text-primary)' }}>{Math.round(local)}%</span>
    </div>
  )
}

export function FitControl({ fit, onChange, disabled }: { fit: string; onChange: (v: string) => void; disabled?: boolean }) {
  const options = [
    { key: 'contain', label: '适配' },
    { key: 'cover', label: '裁切' },
    { key: 'fill', label: '拉伸' },
  ]
  return (
    <div className="flex items-center gap-0.5 rounded-lg p-0.5 shrink-0" style={{ background: 'var(--bg-glass)' }}>
      {options.map((o) => (
        <button
          key={o.key}
          disabled={disabled}
          onClick={() => onChange(o.key)}
          className={`text-[11px] px-2.5 py-1.5 rounded-md font-medium transition-all disabled:opacity-40 border ${
            fit === o.key ? 'selected-surface' : 'hover:opacity-90'
          }`}
          style={fit === o.key
            ? undefined
            : { background: 'transparent', color: 'var(--text-muted)', borderColor: 'transparent' }
          }
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

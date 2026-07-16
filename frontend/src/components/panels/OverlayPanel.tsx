import { useState, useEffect } from 'react'
import { Toggle } from '../ui/Toggle'

const BG_COLORS = [
  { label: '黑', value: '#000000' },
  { label: '白', value: '#FFFFFF' },
  { label: '深灰', value: '#1a1a1a' },
  { label: '浅灰', value: '#e5e5e5' },
  { label: '深蓝', value: '#0f172a' },
  { label: '暖灰', value: '#292524' },
]

interface OverlayPanelProps {
  title: any
  watermark: any
  subtitleFontSize: number
  subtitleEnabled: boolean
  subtitlePosition: string
  bgColor: string
  adjustments?: { brightness: number; contrast: number }
  directoryProgress?: any
  onTitleChange: (t: any) => void
  onWatermarkChange: (w: any) => void
  onSubtitleFontSizeChange: (s: number) => void
  onSubtitleEnabledChange: (v: boolean) => void
  onSubtitlePositionChange: (pos: string) => void
  onBgColorChange: (color: string) => void
  onAdjustmentsChange?: (adj: { brightness: number; contrast: number }) => void
  onDirectoryProgressChange?: (dp: any) => void
}

const SUBTITLE_POSITIONS = [
  { value: 'top_left', label: '↖' },
  { value: 'top_center', label: '↑' },
  { value: 'top_right', label: '↗' },
  { value: 'middle_left', label: '←' },
  { value: 'middle_center', label: '●' },
  { value: 'middle_right', label: '→' },
  { value: 'bottom_left', label: '↙' },
  { value: 'bottom_center', label: '↓' },
  { value: 'bottom_right', label: '↘' },
]

export default function OverlayPanel({
  title, watermark, subtitleFontSize, subtitleEnabled, subtitlePosition, bgColor,
  adjustments = { brightness: 0, contrast: 1 },
  directoryProgress = {},
  onTitleChange, onWatermarkChange, onSubtitleFontSizeChange, onSubtitleEnabledChange,
  onSubtitlePositionChange, onBgColorChange, onAdjustmentsChange, onDirectoryProgressChange
}: OverlayPanelProps) {
  const [titleText, setTitleText] = useState(title.text || '')
  const [watermarkText, setWatermarkText] = useState(watermark.text || '')

  useEffect(() => { setTitleText(title.text || '') }, [title.text])
  useEffect(() => { setWatermarkText(watermark.text || '') }, [watermark.text])

  return (
    <section className="panel-section space-y-4">
      <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-primary)' }}>字幕与画面</h3>

      <div className="space-y-4 pb-4 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>字幕显示</span>
            <Toggle checked={subtitleEnabled} onChange={onSubtitleEnabledChange} />
          </div>
          <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>关闭后只隐藏字幕，配音仍然保留</p>
        </div>

        {subtitleEnabled && (
          <div>
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>字幕字号</span>
              <label className="flex items-center gap-1">
                <input
                  type="number"
                  min={20}
                  max={120}
                  step={2}
                  value={subtitleFontSize}
                  onChange={(e) => onSubtitleFontSizeChange(Math.max(20, Math.min(120, Number(e.target.value) || 48)))}
                  className="input-cinematic w-16 py-1 text-xs text-center font-mono"
                  aria-label="字幕字号"
                />
                <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>px</span>
              </label>
            </div>
            <input
              type="range" min="20" max="120" step="2"
              value={subtitleFontSize}
              onChange={(e) => onSubtitleFontSizeChange(Number(e.target.value))}
              className="w-full" style={{ accentColor: 'var(--accent)' }}
              aria-label="字幕字号滑块"
            />
            <div className="flex justify-between text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
              <span>20</span>
              <span>120</span>
            </div>
          </div>
        )}

        {subtitleEnabled && (
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>字幕位置</span>
              <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>{subtitlePosition.replace('_', ' · ')}</span>
            </div>
            <div className="grid grid-cols-3 gap-1.5 w-fit mx-auto">
              {SUBTITLE_POSITIONS.map(p => (
                <button
                  key={p.value}
                  onClick={() => onSubtitlePositionChange(p.value)}
                  className={`w-9 h-9 rounded-md text-base transition-all ${
                    subtitlePosition === p.value ? 'scale-110' : 'hover:opacity-80'
                  }`}
                  style={subtitlePosition === p.value
                    ? { background: 'var(--accent)', color: 'var(--text-inverse)', boxShadow: '0 0 0 2px var(--accent-bg)' }
                    : { background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-primary)' }
                  }
                  title={p.value}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 背景颜色 */}
      <div>
        <span className="text-sm font-medium block mb-2" style={{ color: 'var(--text-secondary)' }}>背景颜色</span>
        <div className="flex gap-2 items-center">
          {BG_COLORS.map(c => (
            <button
              key={c.value}
              onClick={() => onBgColorChange(c.value)}
              className={`w-8 h-8 rounded-lg border-2 transition-all ${
                bgColor === c.value ? 'scale-110' : 'hover:opacity-80'
              }`}
              style={{
                backgroundColor: c.value,
                borderColor: bgColor === c.value ? 'var(--accent)' : 'var(--border)',
              }}
              title={c.label}
            />
          ))}
          <input
            type="color"
            value={bgColor}
            onChange={(e) => onBgColorChange(e.target.value)}
            className="w-8 h-8 rounded-lg cursor-pointer p-0" style={{ border: '1px solid var(--border)' }}
            title="自定义颜色"
          />
        </div>
      </div>

      {/* 标题 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>标题文字</span>
          <Toggle checked={title.enabled} onChange={(v) => onTitleChange({ ...title, enabled: v })} />
        </div>
        <input
          value={titleText}
          onChange={(e) => setTitleText(e.target.value)}
          onBlur={(e) => onTitleChange({ ...title, text: e.target.value, enabled: true })}
          placeholder="输入标题..."
          disabled={!title.enabled}
          className="input-cinematic"
        />
        {title.enabled && (
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div>
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>字号</span>
              <input type="number" min={16} max={120} step={2}
                value={title.fontSize || 48}
                onChange={(e) => onTitleChange({ ...title, fontSize: Number(e.target.value) })}
                className="input-cinematic text-xs w-full mt-0.5" />
            </div>
            <div>
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>透明度 {Math.round((title.opacity ?? 1) * 100)}%</span>
              <input type="range" min={0} max={1} step={0.05}
                value={title.opacity ?? 1}
                onChange={(e) => onTitleChange({ ...title, opacity: Number(e.target.value) })}
                className="w-full mt-0.5" />
            </div>
          </div>
        )}
      </div>

      {/* 水印 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>水印</span>
          <Toggle checked={watermark.enabled} onChange={(v) => onWatermarkChange({ ...watermark, enabled: v })} />
        </div>
        <input
          value={watermarkText}
          onChange={(e) => setWatermarkText(e.target.value)}
          onBlur={(e) => onWatermarkChange({ ...watermark, text: e.target.value, enabled: true })}
          placeholder="@你的ID..."
          disabled={!watermark.enabled}
          className="input-cinematic"
        />
        {watermark.enabled && (
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div>
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>字号</span>
              <input type="number" min={12} max={80} step={2}
                value={watermark.fontSize || 24}
                onChange={(e) => onWatermarkChange({ ...watermark, fontSize: Number(e.target.value) })}
                className="input-cinematic text-xs w-full mt-0.5" />
            </div>
            <div>
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>透明度 {Math.round((watermark.opacity ?? 0.35) * 100)}%</span>
              <input type="range" min={0.05} max={1} step={0.05}
                value={watermark.opacity ?? 0.35}
                onChange={(e) => onWatermarkChange({ ...watermark, opacity: Number(e.target.value) })}
                className="w-full mt-0.5" />
            </div>
          </div>
        )}
      </div>

      {/* 素材调节 */}
      <div>
        <span className="text-xs font-bold uppercase tracking-wider block mb-2" style={{ color: 'var(--text-primary)' }}>素材调节</span>
        <div className="space-y-3">
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>亮度</span>
              <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>{Math.round(adjustments.brightness * 100)}%</span>
            </div>
            <input type="range" min={-0.5} max={0.5} step={0.01}
              value={adjustments.brightness}
              onChange={(e) => onAdjustmentsChange?.({ ...adjustments, brightness: Number(e.target.value) })}
              className="w-full h-1 accent-[var(--accent)]" />
          </div>
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>对比度</span>
              <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>{Math.round(adjustments.contrast * 100)}%</span>
            </div>
            <input type="range" min={0.5} max={2} step={0.01}
              value={adjustments.contrast}
              onChange={(e) => onAdjustmentsChange?.({ ...adjustments, contrast: Number(e.target.value) })}
              className="w-full h-1 accent-[var(--accent)]" />
          </div>
        </div>
      </div>

      {/* 目录进度条 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium" style={{ color: 'var(--text-secondary)' }}>目录进度条</span>
          <Toggle checked={!!directoryProgress.enabled} onChange={(v) => onDirectoryProgressChange?.({ ...directoryProgress, enabled: v })} />
        </div>
        {directoryProgress.enabled && (
          <div className="space-y-3 rounded-lg p-3" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <textarea
              value={directoryProgress.text || ''}
              onChange={(e) => onDirectoryProgressChange?.({ ...directoryProgress, text: e.target.value })}
              placeholder="起势｜转折｜高潮｜余韵"
              className="input-cinematic min-h-[64px] resize-y text-xs"
            />
            <div className="grid grid-cols-2 gap-2">
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                字号
                <input type="number" min={10} max={80} step={1}
                  value={directoryProgress.fontSize ?? 22}
                  onChange={(e) => onDirectoryProgressChange?.({ ...directoryProgress, fontSize: Number(e.target.value) })}
                  className="input-cinematic text-xs w-full mt-0.5" />
              </label>
              <label className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                颜色
                <input type="color"
                  value={directoryProgress.color || '#F4EBDD'}
                  onChange={(e) => onDirectoryProgressChange?.({ ...directoryProgress, color: e.target.value })}
                  className="w-full h-8 rounded mt-0.5 cursor-pointer" style={{ border: '1px solid var(--border)' }} />
              </label>
            </div>
            <div>
              <div className="flex justify-between text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                <span>透明度</span><span>{Math.round((directoryProgress.opacity ?? 0.72) * 100)}%</span>
              </div>
              <input type="range" min={0.05} max={1} step={0.05}
                value={directoryProgress.opacity ?? 0.72}
                onChange={(e) => onDirectoryProgressChange?.({ ...directoryProgress, opacity: Number(e.target.value) })}
                className="w-full" style={{ accentColor: 'var(--accent)' }} />
            </div>
            <div>
              <div className="flex justify-between text-[10px] mb-1" style={{ color: 'var(--text-muted)' }}>
                <span>底部位置</span><span>{Math.round((directoryProgress.y ?? 0.94) * 100)}%</span>
              </div>
              <input type="range" min={0.78} max={0.98} step={0.01}
                value={directoryProgress.y ?? 0.94}
                onChange={(e) => onDirectoryProgressChange?.({ ...directoryProgress, y: Number(e.target.value) })}
                className="w-full" style={{ accentColor: 'var(--accent)' }} />
            </div>
            <p className="text-[10px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              只覆盖正文配音段：从配音开始移动，到配音结束停止。剪映导出会生成可编辑文字轨；动态预览会烧录移动效果。
            </p>
          </div>
        )}
      </div>

    </section>
  )
}

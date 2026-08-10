import { useState, useEffect, useMemo } from 'react'
import { Microphone, Check, Spinner, Warning, UploadSimple, DownloadSimple, Copy, Plus } from '@phosphor-icons/react'
import AudioPlayer from '../ui/AudioPlayer'
import { LoadingProgress, useProgress } from '../../hooks/useProgress'
import { api } from '../../lib/api'

function splitTextIntoSubtitles(text: string): string[] {
  if (!text.trim()) return []
  const sentenceChunks = text
    .split(/\n+/)
    .flatMap(line => line.split(/([。！？!?；;]+)/))
    .flatMap(chunk => chunk.split(/([，,]+)/))
    .map(s => s.trim())
    .filter(Boolean)

  const out: string[] = []
  for (const part of sentenceChunks) {
    if (part.length <= 20) {
      out.push(part)
      continue
    }

    const chunks = part.split(/([，,]+)/)
    let current = ''
    for (const chunk of chunks) {
      if (!chunk) continue
      if ((current + chunk).length > 20 && current) {
        out.push(current)
        current = chunk
      } else {
        current += chunk
      }
    }
    if (current) out.push(current)
  }
  return out.filter(s => s.trim())
}

const DEFAULT_FISH_PRESETS = [
  { id: '754f3fae6a3b4d8496ab3cfb9a411140', name: '风吟 - 纪录片解说', style: '成熟女声 · 纪录片 · 平静' },
  { id: 'b255ca2902514f69bc22243436a94e4f', name: '曼波', style: '年轻女声 · 教学 · 明亮活力' },
]

const VOLC_API_KEY_URL = 'https://console.volcengine.com/speech/new/setting/apikeys?projectName=default'
const VOLC_SPEAKER_HELP_URL = 'https://docs.volcengine.com/docs/6561/2535742?lang=zh'
const FISH_API_KEY_URL = 'https://fish.audio/app/api-keys'
const FISH_VOICE_HELP_URL = 'https://docs.fish.audio/developer-guide/sdk-guide/python/voice-cloning'

function httpUrl(value: string) {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}

function looksLikeMarkdown(text: string): boolean {
  return /(^|\n)\s{0,3}#{1,6}\s+\S/.test(text)
    || /(^|\n)\s{0,3}>\s+\S/.test(text)
    || /(^|\n)\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)\S/.test(text)
    || /[*_~`]{1,3}\S/.test(text)
    || /\[[^\]\n]+\]\([^\)\n]+\)/.test(text)
    || /(^|\n)\s*```/.test(text)
}

function markdownToNarrationText(source: string): string {
  let text = source
    .replace(/\r\n?/g, '\n')
    .replace(/^\s*---[\s\S]*?---\s*/m, '')
    .replace(/^\s*```[a-z0-9_-]*\s*\n?/gim, '')
    .replace(/\n?\s*```\s*$/g, '')

  text = text
    .replace(/!\[([^\]]*)\]\([^\)]*\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^\)]*\)/g, '$1')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '')

  const lines = text.split('\n').map((line) => {
    let next = line
      .replace(/^\s{0,3}#{1,6}\s+/, '')
      .replace(/^\s{0,3}>\s?/, '')
      .replace(/^\s{0,3}- \[[ xX]\]\s+/, '')
      .replace(/^\s{0,3}(?:[-*+]\s+|\d+[.)]\s+)/, '')
      .replace(/^\s*\|?\s*:?[-]{3,}:?\s*(?:\|\s*:?[-]{3,}:?\s*)+\|?\s*$/, '')

    next = next
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/__([^_]+)__/g, '$1')
      .replace(/~~([^~]+)~~/g, '$1')
      .replace(/`([^`]+)`/g, '$1')
      .replace(/(^|[^\p{L}\p{N}])\*([^*\n]+)\*/gu, '$1$2')
      .replace(/(^|[^\p{L}\p{N}])_([^_\n]+)_/gu, '$1$2')

    if (/^\s*\|/.test(next) && /\|\s*$/.test(next)) {
      next = next.split('|').map(cell => cell.trim()).filter(Boolean).join('，')
    }
    return next.trim()
  })

  return lines
    .join('\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

interface TtsSettings {
  engine: string
  manboApiUrl: string
  manboApiKey: string
  manboApiKeyConfigured?: boolean
  fishApiKey: string
  fishApiKeyConfigured?: boolean
  fishReferenceId: string
  fishModel: string
  fishSpeed: number
  fishVoicePresets?: { id: string; name: string; style: string }[]
  volcApiKey: string
  volcApiKeyConfigured?: boolean
  volcSpeakerId: string
  volcResourceId: string
  volcVoiceName: string
  volcSpeechRate: number
  customApiUrl: string
  customApiKey: string
  customApiKeyConfigured?: boolean
  customVoice: string
  customSpeed: number
  edgeVoice: string
  edgeRate: number
  edgePitch: number
}

export default function ScriptPanel({
  onGenerate, generating, generated, subtitleCount, duration, audioUrl, projectId, ttsSettings, onTtsSettingsChange,
  progress, subtitles, onSubtitleUpdate,
  voiceovers = [], activeVoiceoverId, onSwitchVoiceover, onDeleteVoiceover,
  script = '', onScriptChange, onSrtImported, onSrtError,
}: {
  onGenerate: (t: string, engine: string) => Promise<void>
  generating: boolean
  generated: boolean
  subtitleCount: number
  duration: number
  audioUrl: string
  projectId: string
  ttsSettings: TtsSettings | null
  onTtsSettingsChange: (s: TtsSettings) => void
  progress?: { active: boolean; progress: number; label: string; failed?: boolean }
  subtitles?: any[]
  onSubtitleUpdate?: (idx: number, text: string) => void
  voiceovers?: any[]
  activeVoiceoverId?: string | null
  onSwitchVoiceover?: (id: string) => Promise<void>
  onDeleteVoiceover?: (id: string) => Promise<void>
  script?: string
  onScriptChange?: (text: string) => void
  onSrtImported?: (result: any) => Promise<void> | void
  onSrtError?: (message: string) => void
}) {
  const [text, setText] = useState(script)
  const [showSettings, setShowSettings] = useState(false)
  const [showSubtitles, setShowSubtitles] = useState(false)
  const [showKeys, setShowKeys] = useState(false)
  const [exportingSrt, setExportingSrt] = useState(false)
  const [customVoiceName, setCustomVoiceName] = useState('')
  const [customVoiceStyle, setCustomVoiceStyle] = useState('')
  const [customVoiceSource, setCustomVoiceSource] = useState('')
  const [testStatus, setTestStatus] = useState<{ ok?: boolean; msg: string } | null>(null)
  const [pasteNotice, setPasteNotice] = useState('')
  const srtProgress = useProgress()
  const engine = ttsSettings?.engine || 'edge'

  useEffect(() => { setText(script) }, [script])

  // Auto-save script with debounce
  useEffect(() => {
    if (text === script) return
    const timer = setTimeout(() => {
      onScriptChange?.(text)
    }, 600)
    return () => clearTimeout(timer)
  }, [text, script, onScriptChange])

  const charCount = text.length
  const draftSubtitles = useMemo(() => splitTextIntoSubtitles(text), [text])
  const isLongText = charCount > 500

  const handleScriptPaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const pasted = event.clipboardData?.getData('text/plain') || ''
    if (!pasted || !looksLikeMarkdown(pasted)) return

    const normalized = markdownToNarrationText(pasted)
    if (!normalized || normalized === pasted) return

    event.preventDefault()
    const target = event.currentTarget
    const start = target.selectionStart ?? text.length
    const end = target.selectionEnd ?? text.length
    const next = text.slice(0, start) + normalized + text.slice(end)
    const cursor = start + normalized.length
    setText(next)
    setPasteNotice('已自动转换 Markdown 为纯文案')
    window.setTimeout(() => setPasteNotice(''), 2400)
    window.requestAnimationFrame(() => {
      target.focus()
      target.setSelectionRange(cursor, cursor)
    })
  }

  const fishPresets = useMemo(() => {
    if (ttsSettings?.fishVoicePresets && ttsSettings.fishVoicePresets.length > 0) {
      return ttsSettings.fishVoicePresets
    }
    return DEFAULT_FISH_PRESETS
  }, [ttsSettings?.fishVoicePresets])

  const handleTestFish = async () => {
    if (!(ttsSettings?.fishApiKey || ttsSettings?.fishApiKeyConfigured) || !ttsSettings?.fishReferenceId) {
      setTestStatus({ ok: false, msg: '请先填写 Fish Audio API Key 和 Reference ID' })
      return
    }
    setTestStatus({ msg: '测试中...' })
    try {
      const res = await api.testFishAudio()
      setTestStatus({ ok: res.ok, msg: res.message })
    } catch (e: any) {
      setTestStatus({ ok: false, msg: `测试失败: ${e.message}` })
    }
  }

  const handleTestManbo = async () => {
    if (!(ttsSettings?.manboApiKey || ttsSettings?.manboApiKeyConfigured)) {
      setTestStatus({ ok: false, msg: '请先填写曼波 API Key' })
      return
    }
    setTestStatus({ msg: '测试中...' })
    try {
      const res = await api.testManbo()
      setTestStatus({ ok: res.ok, msg: res.message })
    } catch (e: any) {
      setTestStatus({ ok: false, msg: `测试失败: ${e.message}` })
    }
  }

  const handleTestVolcengine = async () => {
    if (!(ttsSettings?.volcApiKey || ttsSettings?.volcApiKeyConfigured) || !ttsSettings?.volcSpeakerId) {
      setTestStatus({ ok: false, msg: '请先填写火山云 API Key 和 KV 音色 Speaker ID' })
      return
    }
    setTestStatus({ msg: '测试中...' })
    try {
      const res = await api.testVolcengine()
      setTestStatus({ ok: res.ok, msg: res.message })
    } catch (e: any) {
      setTestStatus({ ok: false, msg: `测试失败: ${e.message}` })
    }
  }

  const handleSrtImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    srtProgress.start('正在识别 SRT...')
    try {
      const result = await api.importSrt(projectId, file)
      setText(result.script || '')
      setShowSubtitles(true)
      await onSrtImported?.(result)
      srtProgress.finish(`已导入 ${result.subtitleCount} 条字幕`)
    } catch (error: any) {
      srtProgress.fail('SRT 导入失败')
      onSrtError?.(error?.message || 'SRT 导入失败')
    } finally {
      event.target.value = ''
    }
  }

  const handleSrtExport = async () => {
    setExportingSrt(true)
    try {
      await api.exportSrt(projectId)
    } catch (error: any) {
      onSrtError?.(error?.message || 'SRT 导出失败')
    } finally {
      setExportingSrt(false)
    }
  }

  const handleEngineChange = (nextEngine: string) => {
    if (!ttsSettings) return
    onTtsSettingsChange({ ...ttsSettings, engine: nextEngine })
  }

  const selectFishVoice = (preset: { id: string }) => {
    if (!ttsSettings) return
    onTtsSettingsChange({ ...ttsSettings, engine: 'fish_audio', fishReferenceId: preset.id })
  }

  const handleSaveCustomVoice = () => {
    if (!ttsSettings) return
    const id = customVoiceSource.match(/[a-f0-9]{32}/i)?.[0] || customVoiceSource.trim()
    if (!customVoiceName.trim() || !id) {
      setTestStatus({ ok: false, msg: '请填写音色名称和 Fish Audio 音色链接或 Reference ID' })
      return
    }
    const preset = {
      id,
      name: customVoiceName.trim(),
      style: customVoiceStyle.trim() || '自定义音色',
    }
    const existing = (ttsSettings.fishVoicePresets || []).filter((item: any) => item.id !== id)
    onTtsSettingsChange({
      ...ttsSettings,
      engine: 'fish_audio',
      fishReferenceId: id,
      fishVoicePresets: [...existing, preset],
    })
    setCustomVoiceName('')
    setCustomVoiceStyle('')
    setCustomVoiceSource('')
    setTestStatus({ ok: true, msg: `已保存音色：${preset.name}` })
  }

  const handleCopyVoiceForAi = async () => {
    if (!ttsSettings) return
    const selected = fishPresets.find((preset) => preset.id === ttsSettings.fishReferenceId)
    const prompt = [
      '请帮我在 VideoForge 中配置以下配音音色：',
      `音色名称：${selected?.name || '自定义音色'}`,
      '供应商：Fish Audio',
      `Reference ID：${ttsSettings.fishReferenceId || '未填写'}`,
      `模型：${ttsSettings.fishModel || 's2.1-pro-free'}`,
      `语速：${ttsSettings.fishSpeed ?? 1.0}`,
      '注意：不要修改或索取 API Key。',
    ].join('\n')
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard API unavailable')
      await navigator.clipboard.writeText(prompt)
      setTestStatus({ ok: true, msg: '音色配置已复制，可粘贴给 AI' })
    } catch {
      const textarea = document.createElement('textarea')
      textarea.value = prompt
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      const copied = document.execCommand('copy')
      textarea.remove()
      setTestStatus(copied
        ? { ok: true, msg: '音色配置已复制，可粘贴给 AI' }
        : { ok: false, msg: '复制失败，请检查浏览器剪贴板权限' })
    }
  }

  const hasSubtitles = (subtitles?.length || subtitleCount) > 0
  const subtitleDuration = subtitles?.length ? Number(subtitles[subtitles.length - 1]?.end || 0) : duration

  return (
    <section className="panel-section">
      <div className="flex items-center justify-between gap-3 mb-3">
        <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-primary)' }}>文案 & 配音</h3>
        <label role="button" tabIndex={0} aria-label="导入 SRT 字幕文件" className={`btn-cinematic px-2.5 py-1.5 text-[11px] flex items-center gap-1.5 ${srtProgress.active ? 'opacity-40 pointer-events-none' : 'cursor-pointer'}`} title="导入 SRT 字幕文件">
          {srtProgress.active ? <Spinner size={13} className="animate-spin" /> : <UploadSimple size={13} weight="bold" />}
          导入 SRT
          <input type="file" accept=".srt,application/x-subrip" onChange={handleSrtImport} className="hidden" />
        </label>
      </div>

      <LoadingProgress active={srtProgress.active} progress={srtProgress.progress} label={srtProgress.label} failed={srtProgress.failed} />

      <div className="relative">
        <textarea
          name="scriptText"
          aria-label="旁白文案"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onPaste={handleScriptPaste}
          placeholder="输入旁白文案，生成后会自动对齐字幕..."
          rows={5}
          className="input-cinematic resize-none focus:ring-2 transition-all w-full"
        />
        <div className="absolute bottom-2 right-2 flex items-center gap-2">
          {pasteNotice && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ color: 'var(--text-secondary)', background: 'var(--bg-elevated)' }}>
              {pasteNotice}
            </span>
          )}
          <span className={`text-[10px] px-1.5 py-0.5 rounded-full font-mono ${
            isLongText ? 'bg-rust/20 text-rust-light' : 'bg-transparent'
          }`}>
            {charCount} 字
          </span>
        </div>
      </div>

      <div className="mt-2 flex items-center justify-between text-[10px]" style={{ color: 'var(--text-muted)' }}>
        <div className="flex items-center gap-2">
          {isLongText && (
            <span className="flex items-center gap-1 text-rust-light">
              <Warning size={12} weight="bold" /> 文本较长，将自动分段生成
            </span>
          )}
          {!isLongText && charCount > 0 && (
            <span>预计 {draftSubtitles.length} 条字幕</span>
          )}
        </div>
        <span>建议 50-100 字，单个项目最多支持 50000 字</span>
      </div>

      {/* Subtitle draft preview */}
      {draftSubtitles.length > 0 && !generated && (
        <div className="mt-3 rounded-lg p-2 max-h-40 overflow-y-auto" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          <div className="text-[10px] mb-1.5 flex items-center justify-between" style={{ color: 'var(--text-muted)' }}>
            <span>字幕草稿预览（{draftSubtitles.length} 条）</span>
          </div>
          <div className="space-y-1">
            {draftSubtitles.slice(0, 8).map((sub, idx) => (
              <div key={idx} className="flex items-start gap-2 text-[11px] py-1 px-2 rounded" style={{ background: 'var(--bg-surface)' }}>
                <span className="font-mono shrink-0 w-5 text-right" style={{ color: 'var(--text-muted)' }}>{idx + 1}</span>
                <span style={{ color: 'var(--text-secondary)' }}>{sub}</span>
              </div>
            ))}
            {draftSubtitles.length > 8 && (
              <div className="text-[10px] text-center py-1" style={{ color: 'var(--text-muted)' }}>... 还有 {draftSubtitles.length - 8} 条</div>
            )}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between mt-3">
        <span className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{charCount} 字 · {draftSubtitles.length} 条字幕</span>
        <button
          disabled={!text.trim() || generating}
          onClick={() => onGenerate(text, engine)}
          className="btn-gold rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2 transition-all active:scale-[0.98] shadow-sm"
        >
          {generating
            ? <Spinner size={16} className="animate-spin" weight="bold" />
            : <Microphone size={16} weight="bold" />
          }
          {generating ? '生成中...' : generated ? '生成新版配音' : engine === 'none' ? '生成字幕' : '生成配音'}
        </button>
      </div>

      {progress && <LoadingProgress active={progress.active} progress={progress.progress} label={progress.label} failed={'failed' in progress ? (progress as any).failed : false} />}

      {/* 閰嶉煶寮曟搸閫夋嫨 + 璁剧疆 */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
          {['none', 'edge', 'manbo', 'fish_audio', 'volcengine', 'custom'].map(e => (
          <button key={e}
            onClick={() => handleEngineChange(e)}
            className={`text-[11px] px-2 py-1 rounded-full border font-medium transition-all whitespace-nowrap ${
              engine === e ? 'selected-surface' : 'hover:opacity-90'
            }`}
            style={engine === e ? undefined : { background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
          >
            {e === 'none' ? '无配音' : e === 'edge' ? 'Edge TTS' : e === 'manbo' ? '曼波 VIP' : e === 'fish_audio' ? 'Fish Audio' : e === 'volcengine' ? '火山云' : '自定义 API'}
          </button>
        ))}
        <button onClick={() => setShowSettings(!showSettings)} className="ml-auto text-[11px] underline whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
          {showSettings ? '收起' : '配置'}
        </button>
      </div>

      {engine === 'fish_audio' && ttsSettings && (
        <div className="mt-3 rounded-lg p-3 space-y-3" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>选择音色</div>
              <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>先选你想听的声音，供应商和 API 属于高级配置</div>
            </div>
            <button type="button" onClick={handleCopyVoiceForAi} className="btn-cinematic px-2 py-1 text-[10px] flex items-center gap-1 shrink-0" title="复制不含 API Key 的音色配置">
              <Copy size={12} /> 复制给 AI
            </button>
          </div>

          <div className="grid gap-1.5">
            {fishPresets.map((preset) => (
              <button key={preset.id} type="button" onClick={() => selectFishVoice(preset)}
                className={`w-full text-left rounded-md px-2.5 py-2 text-[11px] transition-all ${ttsSettings.fishReferenceId === preset.id ? 'selected-surface' : 'hover:opacity-90'}`}
                style={ttsSettings.fishReferenceId === preset.id ? undefined : { background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
                <span className="font-semibold flex items-center justify-between">
                  {preset.name}
                  {ttsSettings.fishReferenceId === preset.id && <Check size={13} weight="bold" />}
                </span>
                <span className="block text-[9px] mt-0.5 opacity-75">{preset.style}</span>
              </button>
            ))}
          </div>

          <div className="pt-2 border-t space-y-2" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-1.5 text-[10px] font-semibold" style={{ color: 'var(--text-secondary)' }}>
              <Plus size={12} /> 添加我的音色
            </div>
            <input value={customVoiceName} onChange={(e) => setCustomVoiceName(e.target.value)} placeholder="音色名称，例如：纪录片男声" className="w-full rounded px-2 py-1.5 text-[11px]" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
            <input value={customVoiceStyle} onChange={(e) => setCustomVoiceStyle(e.target.value)} placeholder="风格标签，可选，例如：沉稳 · 低音" className="w-full rounded px-2 py-1.5 text-[11px]" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
            <input value={customVoiceSource} onChange={(e) => setCustomVoiceSource(e.target.value)} placeholder="粘贴 Fish Audio 音色链接或 Reference ID" className="w-full rounded px-2 py-1.5 text-[11px] font-mono" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
            <button type="button" onClick={handleSaveCustomVoice} className="btn-cinematic w-full py-1.5 text-[11px]">保存并使用</button>
          </div>
        </div>
      )}

      {engine === 'volcengine' && ttsSettings && (
        <div className="mt-3 rounded-lg p-3 space-y-3" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          <div>
            <div className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>选择音色</div>
            <div className="text-[10px] mt-0.5" style={{ color: 'var(--text-muted)' }}>豆包声音复刻 2.0 · 使用你在火山云训练的专属音色</div>
          </div>
          <button type="button" onClick={() => handleEngineChange('volcengine')}
            className="w-full text-left rounded-md px-2.5 py-2 text-[11px] selected-surface">
            <span className="font-semibold flex items-center justify-between">
              {ttsSettings.volcVoiceName || 'KV 音色'}
              <Check size={13} weight="bold" />
            </span>
            <span className="block text-[9px] mt-0.5 opacity-75">火山云 · 声音复刻 2.0 · 私人音色</span>
          </button>
          <div className="rounded-md p-3 space-y-2" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between">
              <label htmlFor="volc-speech-rate" className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>配音语速</label>
              <span className="rounded px-2 py-0.5 text-xs font-semibold" style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>
                {((100 + Number(ttsSettings.volcSpeechRate ?? 0)) / 100).toFixed(2)}×
              </span>
            </div>
            <input
              id="volc-speech-rate"
              type="range"
              min="-50"
              max="100"
              step="5"
              value={ttsSettings.volcSpeechRate ?? 0}
              onChange={e => onTtsSettingsChange({ ...ttsSettings, volcSpeechRate: Number(e.target.value) })}
              className="w-full accent-[var(--accent)] cursor-pointer"
              aria-label="火山云配音语速"
            />
            <div className="grid grid-cols-4 gap-1.5">
              {[[-25, '0.75×'], [0, '1.0×'], [25, '1.25×'], [50, '1.5×']].map(([value, label]) => (
                <button key={String(value)} type="button"
                  onClick={() => onTtsSettingsChange({ ...ttsSettings, volcSpeechRate: Number(value) })}
                  className={`rounded px-1.5 py-1.5 text-[11px] font-medium transition-all ${Number(ttsSettings.volcSpeechRate ?? 0) === Number(value) ? 'selected-surface' : ''}`}
                  style={Number(ttsSettings.volcSpeechRate ?? 0) === Number(value) ? undefined : { background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
                  {label}
                </button>
              ))}
            </div>
            <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>选择后自动保存；重新生成配音时生效。</p>
          </div>
        </div>
      )}

      {/* TTS 閰嶇疆灞曞紑 */}
      {showSettings && ttsSettings && (
        <div className="mt-3 rounded-lg p-3 space-y-2 text-xs" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          {engine === 'edge' && (
            <>
            <label className="flex items-center justify-between">
              <span style={{ color: 'var(--text-muted)' }}>语音</span>
              <input value={ttsSettings.edgeVoice} onChange={e => onTtsSettingsChange({ ...ttsSettings, edgeVoice: e.target.value })}
                className="w-44 rounded px-2 py-1 text-[11px]" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
            </label>
            <label className="flex items-center justify-between">
              <span style={{ color: 'var(--text-muted)' }}>语速(%)</span>
              <input
                type="number"
                step="0.1"
                value={ttsSettings.edgeRate ?? 0}
                onChange={e => onTtsSettingsChange({ ...ttsSettings, edgeRate: Number(e.target.value) || 0 })}
                className="w-44 rounded px-2 py-1 text-[11px]"
                style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
            </label>
            <label className="flex items-center justify-between">
              <span style={{ color: 'var(--text-muted)' }}>音调(Hz)</span>
              <input
                type="number"
                step="0.1"
                value={ttsSettings.edgePitch ?? 0}
                onChange={e => onTtsSettingsChange({ ...ttsSettings, edgePitch: Number(e.target.value) || 0 })}
                className="w-44 rounded px-2 py-1 text-[11px]"
                style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
              />
            </label>
            </>
          )}
          {engine === 'manbo' && ttsSettings && (
            <>
              <div className="rounded-md px-2.5 py-2 text-[10px] leading-relaxed" style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                <span>曼波的 API Key 由当前服务商账户提供；本应用没有可确认的统一官网取 Key 页面。 </span>
                {httpUrl(ttsSettings.manboApiUrl) ? (
                  <a href={httpUrl(ttsSettings.manboApiUrl)} target="_blank" rel="noreferrer" className="underline" style={{ color: 'var(--accent)' }}>打开当前服务地址 ↗</a>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>先填入服务商给你的 API URL。</span>
                )}
              </div>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>API URL</span>
                <input value={ttsSettings.manboApiUrl} onChange={e => onTtsSettingsChange({ ...ttsSettings, manboApiUrl: e.target.value })}
                  className="w-44 rounded px-2 py-1 text-[11px]" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
              </label>
              <label className="flex items-center justify-between gap-2">
                <span style={{ color: 'var(--text-muted)' }}>API Key</span>
                <div className="flex items-center gap-1 w-44">
                  <input
                    type={showKeys ? 'text' : 'password'}
                    value={ttsSettings.manboApiKey}
                    onChange={e => onTtsSettingsChange({ ...ttsSettings, manboApiKey: e.target.value })}
                    placeholder={ttsSettings.manboApiKeyConfigured ? '已配置，输入新 Key 可替换' : 'mk-xxxxx'}
                    className="flex-1 rounded px-2 py-1 text-[11px] font-mono"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                  />
                  <button
                    onClick={() => setShowKeys(v => !v)}
                    className="text-[10px] px-1.5 py-1 rounded"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}
                  >
                    {showKeys ? '隐藏' : '显示'}
                  </button>
                </div>
              </label>


              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={handleTestManbo}
                  disabled={!(ttsSettings.manboApiKey || ttsSettings.manboApiKeyConfigured)}
                  className="text-[11px] px-3 py-1.5 rounded transition-all disabled:opacity-40"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                >
                  测试接口
                </button>
                {testStatus && (
                  <span className={"text-[10px] " + (testStatus.ok === false ? 'text-rust-light' : testStatus.ok === true ? 'text-sage' : '')} style={{ color: testStatus.ok === undefined ? 'var(--text-muted)' : undefined }}>
                    {testStatus.msg}
                  </span>
                )}
              </div>
            </>
          )}
          {engine === 'fish_audio' && ttsSettings && (
            <>
              <div className="rounded-md px-2.5 py-2 text-[10px] leading-relaxed space-y-1" style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                <p><a href={FISH_API_KEY_URL} target="_blank" rel="noreferrer" className="underline" style={{ color: 'var(--accent)' }}>获取 Fish Audio API Key ↗</a>：登录后在 API Keys 页面新建或复制。</p>
                <p><a href={FISH_VOICE_HELP_URL} target="_blank" rel="noreferrer" className="underline" style={{ color: 'var(--accent)' }}>查看音色 / Reference ID 说明 ↗</a>：把音色的 Reference ID 填在下方。</p>
              </div>
              <label className="flex items-center justify-between gap-2">
                <span style={{ color: 'var(--text-muted)' }}>API Key</span>
                <div className="flex items-center gap-1 w-44">
                  <input
                    type={showKeys ? 'text' : 'password'}
                    value={ttsSettings.fishApiKey}
                    onChange={e => onTtsSettingsChange({ ...ttsSettings, fishApiKey: e.target.value })}
                    placeholder={ttsSettings.fishApiKeyConfigured ? '已配置，输入新 Key 可替换' : 'fk-xxxxx'}
                    className="flex-1 rounded px-2 py-1 text-[11px] font-mono"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                  />
                  <button
                    onClick={() => setShowKeys(v => !v)}
                    className="text-[10px] px-1.5 py-1 rounded"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}
                  >
                    {showKeys ? '隐藏' : '显示'}
                  </button>
                </div>
              </label>

              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>语速 (1.0 = 原速)</span>
                <input
                  type="number"
                  step="0.1"
                  value={ttsSettings.fishSpeed ?? 1.0}
                  onChange={e => onTtsSettingsChange({ ...ttsSettings, fishSpeed: Number(e.target.value) || 0 })}
                  className="w-44 rounded px-2 py-1 text-[11px]"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                />
              </label>

              <div>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>Reference ID</span>
                <input value={ttsSettings.fishReferenceId} onChange={e => onTtsSettingsChange({ ...ttsSettings, fishReferenceId: e.target.value })}
                  placeholder="754f3fae6a3b4d8496ab3cfb9a411140"
                  className="w-44 rounded px-2 py-1 text-[11px] font-mono"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
              </label>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>Model</span>
                <select value={ttsSettings.fishModel} onChange={e => onTtsSettingsChange({ ...ttsSettings, fishModel: e.target.value })}
                  className="w-44 rounded px-2 py-1 text-[11px]"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
                  <option value="s2.1-pro-free">s2.1-pro-free（免费）</option>
                  <option value="s2-pro">s2-pro</option>
                  <option value="s2.1-pro">s2.1-pro</option>
                </select>
              </label>

              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={handleTestFish}
                  disabled={!(ttsSettings.fishApiKey || ttsSettings.fishApiKeyConfigured) || !ttsSettings.fishReferenceId}
                  className="text-[11px] px-3 py-1.5 rounded transition-all disabled:opacity-40"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                >
                  测试接口
                </button>
                {testStatus && (
                  <span className={`text-[10px] ${testStatus.ok === false ? 'text-rust-light' : testStatus.ok === true ? 'text-sage' : ''}`} style={{ color: testStatus.ok === undefined ? 'var(--text-muted)' : undefined }}>
                    {testStatus.msg}
                  </span>
                )}
              </div>
              </div>
            </>
          )}
          {engine === 'volcengine' && ttsSettings && (
            <>
              <div className="rounded-md px-2.5 py-2 text-[10px] leading-relaxed space-y-1" style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                <p><a href={VOLC_API_KEY_URL} target="_blank" rel="noreferrer" className="underline font-medium" style={{ color: 'var(--accent)' }}>获取新版火山云 API Key ↗</a>：登录后在“API Key 管理”创建并复制。</p>
                <p>这里仅填 <strong>新版 API Key</strong>；旧版的 App ID、Access Token、Secret Key 都不是此接口要的凭证，填入会返回 401。</p>
                <p><a href={VOLC_SPEAKER_HELP_URL} target="_blank" rel="noreferrer" className="underline" style={{ color: 'var(--accent)' }}>查看音色与 Speaker ID 说明 ↗</a>：KV 音色的 Speaker ID 已为你填好。</p>
              </div>
              <label className="flex items-center justify-between gap-2">
                <span style={{ color: 'var(--text-muted)' }}>API Key</span>
                <div className="flex items-center gap-1 w-44">
                  <input
                    type={showKeys ? 'text' : 'password'}
                    value={ttsSettings.volcApiKey}
                    onChange={e => onTtsSettingsChange({ ...ttsSettings, volcApiKey: e.target.value })}
                    placeholder={ttsSettings.volcApiKeyConfigured ? '已配置，输入新 Key 可替换' : '粘贴火山云 API Key'}
                    className="flex-1 rounded px-2 py-1 text-[11px] font-mono"
                    style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                  />
                  <button onClick={() => setShowKeys(v => !v)} className="text-[10px] px-1.5 py-1 rounded" style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>
                    {showKeys ? '隐藏' : '显示'}
                  </button>
                </div>
              </label>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>KV Speaker ID</span>
                <input
                  value={ttsSettings.volcSpeakerId}
                  onChange={e => onTtsSettingsChange({ ...ttsSettings, volcSpeakerId: e.target.value.trim() })}
                  placeholder="S_xxxxx（火山云音色库）"
                  className="w-44 rounded px-2 py-1 text-[11px] font-mono"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                />
              </label>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>音色名称</span>
                <input
                  value={ttsSettings.volcVoiceName || 'KV 音色'}
                  onChange={e => onTtsSettingsChange({ ...ttsSettings, volcVoiceName: e.target.value })}
                  className="w-44 rounded px-2 py-1 text-[11px]"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                />
              </label>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>模型</span>
                <input
                  value={ttsSettings.volcResourceId || 'seed-icl-2.0'}
                  onChange={e => onTtsSettingsChange({ ...ttsSettings, volcResourceId: e.target.value.trim() || 'seed-icl-2.0' })}
                  className="w-44 rounded px-2 py-1 text-[11px] font-mono"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                />
              </label>
              <div className="flex items-center gap-2 pt-1">
                <button
                  onClick={handleTestVolcengine}
                  disabled={!(ttsSettings.volcApiKey || ttsSettings.volcApiKeyConfigured) || !ttsSettings.volcSpeakerId}
                  className="text-[11px] px-3 py-1.5 rounded transition-all disabled:opacity-40"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                >
                  测试 KV 音色
                </button>
                {testStatus && (
                  <span className={`text-[10px] ${testStatus.ok === false ? 'text-rust-light' : testStatus.ok === true ? 'text-sage' : ''}`} style={{ color: testStatus.ok === undefined ? 'var(--text-muted)' : undefined }}>
                    {testStatus.msg}
                  </span>
                )}
              </div>
            </>
          )}
          {engine === 'custom' && (
            <>
              <div className="rounded-md px-2.5 py-2 text-[10px] leading-relaxed" style={{ background: 'var(--bg-surface)', color: 'var(--text-secondary)', border: '1px solid var(--border)' }}>
                自定义 API 的 URL、Key 和音色字段由你选择的服务商定义。请在该服务商控制台获取 Key；
                {httpUrl(ttsSettings?.customApiUrl || '') ? (
                  <a href={httpUrl(ttsSettings?.customApiUrl || '')} target="_blank" rel="noreferrer" className="underline" style={{ color: 'var(--accent)' }}>打开当前接口地址 ↗</a>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>填入 API URL 后可直接打开该地址。</span>
                )}
              </div>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>API URL</span>
                <input value={ttsSettings.customApiUrl} onChange={e => onTtsSettingsChange({ ...ttsSettings, customApiUrl: e.target.value })}
                  className="w-44 rounded px-2 py-1 text-[11px]" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
              </label>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>API Key</span>
                <input type="password" value={ttsSettings.customApiKey} onChange={e => onTtsSettingsChange({ ...ttsSettings, customApiKey: e.target.value })}
                  placeholder={ttsSettings.customApiKeyConfigured ? '已配置，输入新 Key 可替换' : 'API Key'}
                  className="w-44 rounded px-2 py-1 text-[11px]" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }} />
              </label>
              <label className="flex items-center justify-between">
                <span style={{ color: 'var(--text-muted)' }}>语速</span>
                <input
                  type="number"
                  step="0.1"
                  value={ttsSettings.customSpeed ?? 0}
                  onChange={e => onTtsSettingsChange({ ...ttsSettings, customSpeed: Number(e.target.value) || 0 })}
                  className="w-44 rounded px-2 py-1 text-[11px]"
                  style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                />
              </label>
            </>
          )}
        </div>
      )}

      {/* 閰嶉煶鍒楄〃 */}
      {voiceovers.length > 0 && (
        <div className="mt-3 rounded-lg p-2 space-y-1.5" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-secondary)' }}>配音版本 {voiceovers.length} 个</span>
          </div>
          {voiceovers.map((vo: any) => {
            const isActive = vo.id === activeVoiceoverId
            const engineMap = { edge: 'Edge', manbo: '曼波', fish_audio: 'Fish', custom: '自定义' } as const
            const engineLabel = engineMap[(vo.engine as keyof typeof engineMap)] || vo.engine
            return (
              <div key={vo.id} className={`flex items-center gap-2 rounded px-2 py-1.5 text-[11px] transition-all ${isActive ? 'border border-gold/40 bg-gold/5' : ''}`}
                style={{ background: isActive ? undefined : 'var(--bg-surface)' }}>
                <button
                  onClick={() => onSwitchVoiceover?.(vo.id)}
                  className={`w-5 h-5 rounded-full flex items-center justify-center shrink-0 transition-all ${isActive ? 'selected-surface' : ''}`}
                  style={isActive ? undefined : { border: '1px solid var(--border-subtle)', color: 'var(--text-muted)', background: 'var(--bg-surface)' }}
                  title={isActive ? '当前激活' : '切换到此配音'}
                >
                  {isActive && <span className="text-[9px]">✓</span>}
                </button>
                <div className="flex-1 min-w-0">
                  <p className="truncate" style={{ color: 'var(--text-primary)' }}>{engineLabel} · {vo.duration?.toFixed?.(1) || 0}s</p>
                  <p className="truncate text-[10px]" style={{ color: 'var(--text-muted)' }}>{vo.text?.slice(0, 24) || '无文案'}{vo.text?.length > 24 ? '...' : ''}</p>
                </div>
                {voiceovers.length > 1 && (
                  <button
                    onClick={() => onDeleteVoiceover?.(vo.id)}
                    className="shrink-0 text-[10px] px-1.5 py-0.5 rounded hover:opacity-80 transition-all"
                    style={{ color: 'var(--rust)' }}
                  >
                    删除
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* 閰嶉煶鎾斁鍣?*/}
      {generated && audioUrl && (
        <div className="mt-3">
          <AudioPlayer key={audioUrl} src={audioUrl} />
        </div>
      )}

      {(generated || hasSubtitles) && (
        <div className="mt-2 flex items-center justify-between gap-2 text-xs font-medium rounded-lg px-3 py-2" style={{ background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>
          <div className="flex items-center gap-3 min-w-0">
            <span className="whitespace-nowrap">时长 {subtitleDuration.toFixed(1)}s</span>
            <button type="button" onClick={() => setShowSubtitles(v => !v)} className="hover:underline cursor-pointer px-1 rounded whitespace-nowrap" style={{ color: 'var(--text-primary)' }}>
              字幕 {subtitles?.length || subtitleCount} 条 {showSubtitles ? '▼' : '▶'}
            </button>
          </div>
          <button
            type="button"
            onClick={handleSrtExport}
            disabled={!hasSubtitles || exportingSrt}
            className="btn-gold px-2.5 py-1.5 text-[11px] flex items-center gap-1.5 shrink-0 disabled:opacity-40"
            title="导出当前字幕为 SRT"
          >
            {exportingSrt ? <Spinner size={13} className="animate-spin" /> : <DownloadSimple size={13} weight="bold" />}
            {exportingSrt ? '导出中' : '导出 SRT'}
          </button>
        </div>
      )}

      {hasSubtitles && showSubtitles && (
        <div className="mt-1 max-h-48 overflow-y-auto rounded-lg p-2 space-y-1" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
          {(subtitles || []).length > 0 ? (subtitles || []).map((sub: any, idx: number) => (
            <div key={idx} className="flex items-start gap-2 text-[11px] py-1 px-2 rounded" style={{ background: 'var(--bg-surface)' }}>
              <span className="font-mono shrink-0 w-6 text-right" style={{ color: 'var(--text-muted)' }}>{idx + 1}</span>
              <textarea
                rows={Math.min(2, Math.max(1, String(sub.text || '').split('\n').length))}
                className="flex-1 bg-transparent border-none outline-none text-[11px] p-0 resize-none leading-4"
                style={{ color: 'var(--text-primary)' }}
                value={sub.text}
                onChange={(e) => onSubtitleUpdate?.(idx, e.target.value)}
              />
              <span className="font-mono shrink-0 text-[9px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                {sub.start?.toFixed(1)}s - {sub.end?.toFixed(1)}s
              </span>
            </div>
          )) : (
            <div className="text-[11px] py-2 text-center" style={{ color: 'var(--text-muted)' }}>暂无字幕。请先生成配音或导入 SRT。</div>
          )}
        </div>
      )}
    </section>
  )
}

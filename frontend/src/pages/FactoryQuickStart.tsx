import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, WarningCircle } from '@phosphor-icons/react'
import { api } from '../lib/api'

const normalizeStructuredMarkdown = (source: string) => {
  const trimmed = source.trim()
  if (/^\s*(?:##\s+|\[[A-Z_]+\])/m.test(trimmed)) return trimmed
  return `## STORY\n${trimmed}`
}

const safeKey = (prefix: string) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

export default function FactoryQuickStart() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [source, setSource] = useState('')
  const [acceptedFishCall, setAcceptedFishCall] = useState(false)
  const [batchId, setBatchId] = useState('')
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const structuredSource = useMemo(() => normalizeStructuredMarkdown(source), [source])
  const sourceHasStructure = /^\s*(?:##\s+|\[[A-Z_]+\])/m.test(source)

  useEffect(() => {
    if (!batchId) return
    let closed = false
    const refresh = async () => {
      try {
        const batch = await api.getTemplateProductionBatch(batchId)
        const item = batch.items?.[0]
        if (!item || closed) return
        setStatus(item.status || batch.status || '')
        if (item.status === 'awaiting_visual_assets' || item.status === 'ready_to_resume') {
          navigate(`/factory/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(item.itemId)}/visuals`, { replace: true })
        }
        if (item.status === 'failed') setError(item.error || '任务没有完成，请检查配音设置后重试。')
      } catch (requestError: any) {
        if (!closed) setError(requestError.message || '无法读取产片任务状态。')
      }
    }
    refresh()
    const timer = window.setInterval(refresh, 1500)
    return () => { closed = true; window.clearInterval(timer) }
  }, [batchId, navigate])

  const start = async () => {
    if (!name.trim() || !source.trim() || !acceptedFishCall) return
    setBusy(true); setError(''); setStatus('queued')
    const itemId = safeKey('item')
    try {
      const result = await api.startTemplateProductionBatch({
        schemaVersion: 1,
        name: name.trim(),
        idempotencyKey: safeKey('quick_factory'),
        templateId: 'tpl_single_voiceover',
        defaults: {
          inputMode: 'structured_markdown',
          voiceover: { enabled: true, engine: 'fish_audio', generateSubtitles: true },
          outputs: { preview: true, jianyingDirect: true, jianyingZip: false },
          continueOnError: true,
          maxRetries: 0,
          concurrency: 1,
        },
        visualWorkflow: {
          enabled: true,
          mode: 'generation_pack',
          planningMode: 'fixed_units',
          unitsPerScene: 5,
          targetDuration: 5,
          minDuration: 1,
          maxDuration: 10,
          requireCompleteCoverage: true,
        },
        items: [{ itemId, name: name.trim(), structuredMarkdown: structuredSource, assets: { images: [], videos: [], bgm: null } }],
      })
      setBatchId(result.batchId)
    } catch (requestError: any) {
      setError(requestError.message || '无法创建产片任务。')
      setBusy(false)
    }
  }

  return <main className="min-h-[100dvh] workbench-shell p-6"><div className="max-w-3xl mx-auto space-y-5">
    <header className="flex items-center gap-3"><button className="icon-button" onClick={() => navigate('/')} aria-label="返回首页"><ArrowLeft size={18} /></button><div><p className="section-index">FACTORY / QUICK START</p><h1 className="text-2xl font-heading">文案到素材配对</h1></div></header>
    <section className="card-cinematic p-5 space-y-4">
      <div><h2 className="label-cinematic">一步生成可配图时间线</h2><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>系统会生成带时间戳的配音与字幕，再按字幕时间创建 Scene；进入配图台后可批量上传你已生成的图片或视频。</p></div>
      <label className="block text-xs">视频名称<input className="input-cinematic w-full mt-1" value={name} onChange={event => setName(event.target.value)} placeholder="例如：夏季护肤三条原则" /></label>
      <label className="block text-xs">文案<textarea className="input-cinematic w-full min-h-[280px] mt-1 text-sm" value={source} onChange={event => setSource(event.target.value)} placeholder={'可直接粘贴完整文案。\n\n也可使用：\n## HOOK\n开头内容\n\n## STORY\n正文内容'} /></label>
      {!sourceHasStructure && source.trim() && <div className="status-pill" data-tone="warn"><WarningCircle size={15} />未检测到结构标题：本次会按一个 STORY Block 处理；可在“创建结构化内容”中做更细的 Block 编排。</div>}
      {sourceHasStructure && <div className="status-pill" data-tone="ok"><Check size={15} />已检测到结构标题，会保留你的 Block 结构。</div>}
      <label className="flex gap-2 items-start rounded-lg p-3 text-xs" style={{ background: 'var(--bg-elevated)' }}><input className="mt-0.5" type="checkbox" checked={acceptedFishCall} onChange={event => setAcceptedFishCall(event.target.checked)} /><span>我确认使用已配置的 Fish Audio API 生成带时间戳配音和字幕；这一步会产生真实 API 调用，并可能消耗额度。</span></label>
      {error && <div className="operation-error">{error}</div>}
      {batchId && !error && <div className="status-pill">正在准备时间轴和素材清单：{status || 'queued'}。完成后会自动进入配图台。</div>}
      <div className="flex justify-end"><button className="btn-gold" disabled={!name.trim() || !source.trim() || !acceptedFishCall || busy} onClick={start}>{busy ? '正在创建任务…' : '生成配图任务'} <ArrowRight size={16} /></button></div>
    </section>
  </div></main>
}

import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, CircleNotch, Pause, Play, WarningCircle } from '@phosphor-icons/react'
import { api } from '../lib/api'

const normalizeStructuredMarkdown = (source: string) => {
  const trimmed = source.trim()
  if (/^\s*(?:##\s+|\[[A-Z_]+\])/m.test(trimmed)) return trimmed
  return `## STORY\n${trimmed}`
}

const safeKey = (prefix: string) => `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

const phases = [
  ['creating_project', '创建项目'],
  ['generating_voiceover', '生成配音'],
  ['aligning_subtitles', '对齐字幕'],
  ['planning_visual_scenes', '规划 Scene'],
  ['selecting_visual_provider', '选择视觉 Provider'],
  ['generating_visuals', '生成视觉'],
  ['awaiting_visual_approval', '等待视觉审批'],
  ['binding_visuals', '绑定视觉'],
  ['rendering_preview', '生成 Preview'],
  ['exporting_jianying', '生成剪映草稿'],
  ['done', '完成'],
] as const

export default function FactoryQuickStart() {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [source, setSource] = useState('')
  const [mode, setMode] = useState<'auto' | 'review'>('auto')
  const [profileId, setProfileId] = useState('balanced_auto')
  const [voiceEngine, setVoiceEngine] = useState<'edge' | 'none'>('edge')
  const [profiles, setProfiles] = useState<any[]>([])
  const [batchId, setBatchId] = useState('')
  const [batch, setBatch] = useState<any>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const structuredSource = useMemo(() => normalizeStructuredMarkdown(source), [source])
  const sourceHasStructure = /^\s*(?:##\s+|\[[A-Z_]+\])/m.test(source)

  useEffect(() => { api.getProductionProfiles().then(setProfiles).catch(() => setProfiles([])) }, [])

  useEffect(() => {
    if (!batchId) return
    let closed = false
    const refresh = async () => {
      try {
        const value = await api.getTemplateProductionBatch(batchId)
        if (closed) return
        setBatch(value)
        const item = value.items?.[0]
        if (item?.status === 'awaiting_visual_approval') {
          navigate(`/factory/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(item.itemId)}/visuals`, { replace: true })
        }
      } catch (requestError: any) {
        if (!closed) setError(requestError.message || '无法读取生产状态')
      }
    }
    refresh()
    const timer = window.setInterval(refresh, 900)
    return () => { closed = true; window.clearInterval(timer) }
  }, [batchId, navigate])

  const start = async () => {
    if (!name.trim() || !source.trim() || busy) return
    setBusy(true); setError(''); setBatch(null)
    const itemId = safeKey('item')
    try {
      const result = await api.startTemplateProductionBatch({
        schemaVersion: 1,
        name: name.trim(),
        idempotencyKey: safeKey('autonomous_factory'),
        templateId: 'tpl_single_voiceover',
        productionMode: mode,
        productionProfile: profileId,
        defaults: {
          inputMode: 'structured_markdown',
          voiceover: { enabled: true, engine: voiceEngine, generateSubtitles: true },
          outputs: { preview: true, jianyingDirect: true, jianyingZip: false },
          continueOnError: true,
          maxRetries: 0,
          concurrency: 1,
        },
        visualWorkflow: {
          enabled: true,
          mode: 'generation_pack',
          planningMode: 'target_duration',
          targetDuration: 6,
          minDuration: 2,
          maxDuration: 10,
          requireCompleteCoverage: true,
        },
        items: [{ itemId, name: name.trim(), structuredMarkdown: structuredSource, assets: { images: [], videos: [], bgm: null } }],
      })
      setBatchId(result.batchId)
    } catch (requestError: any) {
      setError(requestError.message || '无法创建生产任务')
      setBusy(false)
    }
  }

  const item = batch?.items?.[0]
  const currentPhase = item?.phase || batch?.status || 'queued'
  const phaseIndex = Math.max(0, phases.findIndex(([key]) => key === currentPhase))
  const completed = item?.status === 'succeeded'
  const paused = item?.status === 'awaiting_visual_approval'

  return <main className="min-h-[100dvh] workbench-shell p-6"><div className="max-w-4xl mx-auto space-y-5">
    <header className="flex items-center gap-3"><button className="icon-button" onClick={() => navigate('/')} aria-label="返回"><ArrowLeft size={18} /></button><div><p className="section-index">FACTORY / AUTONOMOUS V3</p><h1 className="text-2xl font-heading">一键生产视频</h1></div></header>
    {!batchId && <section className="card-cinematic p-5 space-y-5">
      <div><h2 className="text-xl font-heading">从文案到 Preview + 剪映</h2><p className="text-xs mt-2" style={{ color: 'var(--text-muted)' }}>VideoForge 会自动完成配音、字幕、Scene、视觉生成、审批、绑定和输出。高级 VisualPlan 与 Provider 细节会在需要时展开。</p></div>
      <label className="block text-xs">视频名称<input className="input-cinematic w-full mt-1" value={name} onChange={event => setName(event.target.value)} placeholder="例如：夏季护肤三条原则" /></label>
      <label className="block text-xs">完整文案<textarea className="input-cinematic w-full min-h-[300px] mt-1 text-sm" value={source} onChange={event => setSource(event.target.value)} placeholder={'直接粘贴完整中文文案。\n\n也可使用结构标题：\n## HOOK\n开头内容\n## STORY\n正文内容'} /></label>
      {!sourceHasStructure && source.trim() && <div className="status-pill" data-tone="warn"><WarningCircle size={15} />未检测到结构标题，将按一个 STORY Block 处理。</div>}
      {sourceHasStructure && <div className="status-pill" data-tone="ok"><Check size={15} />已检测到结构标题，将保留 Block 结构。</div>}
      <div className="grid md:grid-cols-2 gap-3">
        <label className="text-xs">Production Profile<select className="input-cinematic w-full mt-1" value={profileId} onChange={event => setProfileId(event.target.value)}>{(profiles.length ? profiles : [{ id: 'balanced_auto', name: 'Balanced Auto', description: 'Auto Router' }]).map(profile => <option key={profile.id} value={profile.id}>{profile.name}</option>)}</select><span className="block mt-1" style={{ color: 'var(--text-muted)' }}>{profiles.find(profile => profile.id === profileId)?.description || 'Auto Router 按语义选择本地 Provider'}</span></label>
        <label className="text-xs">配音引擎<select className="input-cinematic w-full mt-1" value={voiceEngine} onChange={event => setVoiceEngine(event.target.value as 'edge' | 'none')}><option value="edge">Edge TTS（本地免费）</option><option value="none">无配音（只生成字幕 timing）</option></select></label>
      </div>
      <div className="flex flex-wrap gap-2"><button className={mode === 'auto' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => setMode('auto')}><Play size={14} /> AUTO：本地 Provider 自动批准</button><button className={mode === 'review' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => setMode('review')}><Pause size={14} /> REVIEW：批量审查视觉</button></div>
      {error && <div className="operation-error">{error}</div>}
      <div className="flex justify-end"><button className="btn-gold" disabled={!name.trim() || !source.trim() || busy} onClick={start}>{busy ? <CircleNotch className="animate-spin" size={16} /> : <ArrowRight size={16} />} {busy ? '正在启动生产…' : '生成视频'}</button></div>
    </section>}
    {batchId && <section className="card-cinematic p-5 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="section-index">RUN PROGRESS</p><h2 className="text-xl font-heading">{name || '视频生产任务'}</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Batch {batchId} · {mode.toUpperCase()} · {profileId}</p></div><span className="status-pill" data-tone={completed ? 'ok' : paused ? 'warn' : 'warn'}>{item?.status || batch?.status || 'queued'}</span></div>
      <div className="space-y-2">{phases.map(([key, label], index) => <div key={key} className="flex items-center gap-3 text-sm"><span className={`w-6 h-6 rounded-full grid place-items-center text-xs ${index < phaseIndex || completed ? 'bg-[var(--accent)] text-white' : index === phaseIndex ? 'border border-[var(--accent)]' : 'border'}`}>{index < phaseIndex || completed ? '✓' : index + 1}</span><span style={{ color: index <= phaseIndex || completed ? 'var(--text-primary)' : 'var(--text-muted)' }}>{label}</span>{index === phaseIndex && !completed && !paused && <CircleNotch className="animate-spin ml-auto" size={15} />}</div>)}</div>
      {paused && <div className="rounded-lg p-4" style={{ background: 'var(--bg-elevated)' }}><p className="font-semibold">生产已暂停：等待视觉审批</p><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>进入 Review All Visuals 后，可以批量接受、替换 Candidate、重生成或覆盖 Provider。批准后会自动继续 Preview 与剪映草稿。</p></div>}
      {completed && <div className="rounded-lg p-4 space-y-2" style={{ background: 'var(--bg-elevated)' }}><p className="font-semibold">视频生产完成</p><p className="text-xs" style={{ color: 'var(--text-muted)' }}>Scene coverage 已完成，Preview 和 JianYing draft 已生成。</p><div className="flex gap-2"><button className="btn-gold text-xs" onClick={() => item?.projectId && navigate(`/editor/${item.projectId}`)}>打开项目</button></div></div>}
      {item?.error && <div className="operation-error">{item.error}</div>}
    </section>}
  </div></main>
}

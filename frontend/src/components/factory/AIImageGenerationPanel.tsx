import { useEffect, useMemo, useState } from 'react'
import { CheckCircle, DownloadSimple, Images, Play, Spinner, Wrench } from '@phosphor-icons/react'
import { api } from '../../lib/api'

type SceneInput = {
  sceneId: string
  blockId: string
  start: number
  end: number
  duration: number
  text: string
  prompt: string
  negativePrompt: string
}

type Props = {
  projectId: string
  scenes: SceneInput[]
  onBound: () => Promise<void> | void
  onMessage: (message: string) => void
}

type SceneDraft = SceneInput & { enabled: boolean }

const blankProvider = {
  enabled: false,
  providerId: 'openai-compatible',
  baseUrl: '',
  apiKey: '',
  apiKeyConfigured: false,
  model: '',
  timeoutSeconds: 120,
  maxConcurrency: 4,
}

const batchStorageKey = (projectId: string) => `videoforge:image-batch:${projectId}`

export default function AIImageGenerationPanel({ projectId, scenes, onBound, onMessage }: Props) {
  const [channel, setChannel] = useState<'builtin' | 'agent' | 'local'>('local')
  const [drafts, setDrafts] = useState<SceneDraft[]>([])
  const [provider, setProvider] = useState<any>(blankProvider)
  const [styleAnchor, setStyleAnchor] = useState('cinematic, low-saturation, warm mid-century color palette')
  const [continuityAnchor, setContinuityAnchor] = useState('')
  const [candidateCount, setCandidateCount] = useState(1)
  const [paidConfirmed, setPaidConfirmed] = useState(false)
  const [batch, setBatch] = useState<any>(null)
  const [selectedCandidates, setSelectedCandidates] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')

  useEffect(() => {
    setDrafts(scenes.map(scene => ({ ...scene, enabled: Boolean(scene.prompt?.trim() || scene.text?.trim()) })))
  }, [scenes])

  useEffect(() => {
    api.getAIImageProviderSettings().then(setProvider).catch(() => onMessage('AI 生图 Provider 设置读取失败'))
    const remembered = localStorage.getItem(batchStorageKey(projectId))
    if (remembered) api.getImageGenerationBatch(projectId, remembered).then(setBatch).catch(() => localStorage.removeItem(batchStorageKey(projectId)))
  }, [projectId, onMessage])

  useEffect(() => {
    const selections: Record<string, string> = {}
    for (const item of batch?.items || []) {
      const candidate = item.candidates?.find((value: any) => value.status === 'selected') || item.candidates?.[0]
      if (candidate) selections[item.sceneId] = candidate.candidateId
    }
    setSelectedCandidates(selections)
  }, [batch])

  const selectedCount = drafts.filter(scene => scene.enabled && Boolean(scene.prompt.trim() || scene.text.trim())).length
  const generatedCount = useMemo(() => (batch?.items || []).filter((item: any) => item.candidates?.length).length, [batch])

  const updateScene = (sceneId: string, patch: Partial<SceneDraft>) => {
    setDrafts(values => values.map(value => value.sceneId === sceneId ? { ...value, ...patch } : value))
  }

  const saveProvider = async () => {
    setBusy('provider')
    try {
      const saved = await api.updateAIImageProviderSettings(provider)
      setProvider((current: any) => ({ ...current, ...saved, apiKey: '' }))
      onMessage('AI 生图 Provider 设置已保存在本机')
    } catch (error: any) { onMessage(error.message || 'Provider 设置保存失败') }
    finally { setBusy('') }
  }

  const testProvider = async () => {
    setBusy('test')
    try {
      const result = await api.testAIImageProvider(provider)
      onMessage(result.message || 'Provider 连接成功')
    } catch (error: any) { onMessage(error.message || 'Provider 连接失败') }
    finally { setBusy('') }
  }

  const refreshBatch = async (batchId = batch?.batchId) => {
    if (!batchId) return
    const value = await api.getImageGenerationBatch(projectId, batchId)
    setBatch(value)
    return value
  }

  const pollJob = async (jobId: string, batchId: string) => {
    const tick = async () => {
      try {
        const job = await api.getJob(jobId)
        await refreshBatch(batchId)
        if (job.status === 'queued' || job.status === 'running') {
          window.setTimeout(tick, 900)
        } else {
          setBusy('')
          onMessage(job.status === 'succeeded' ? '图片候选已生成，请确认后绑定' : (job.error || 'AI 生图任务失败'))
        }
      } catch (error: any) { setBusy(''); onMessage(error.message || '生图任务状态读取失败') }
    }
    await tick()
  }

  const start = async () => {
    if (!selectedCount) return onMessage('请至少选择一个含 Prompt 的 Scene')
    if (channel === 'builtin' && !paidConfirmed) return onMessage('请先确认本次外接 API 可能消耗额度')
    setBusy('create')
    try {
      if (channel === 'builtin') await api.updateAIImageProviderSettings(provider)
      const sceneOverrides = Object.fromEntries(drafts.filter(value => value.enabled).map(value => [value.sceneId, { prompt: value.prompt, negativePrompt: value.negativePrompt }]))
      const created = await api.createImageGenerationBatch(projectId, {
        channel,
        providerId: channel === 'agent' ? 'codex-imagegen' : channel === 'local' ? 'stickman' : provider.providerId,
        model: channel === 'builtin' ? provider.model : '',
        candidateCount,
        styleAnchor,
        continuityAnchor,
        sceneIds: drafts.filter(value => value.enabled).map(value => value.sceneId),
        sceneOverrides,
      })
      setBatch(created); localStorage.setItem(batchStorageKey(projectId), created.batchId)
      if (channel === 'agent') {
        setBusy(''); onMessage(`Agent 生图任务已创建：${created.items.length} 个 Scene`)
      } else {
        const result = await api.runImageGenerationBatch(projectId, created.batchId)
        setBusy('generate'); await pollJob(result.job.jobId, created.batchId)
      }
    } catch (error: any) { setBusy(''); onMessage(error.message || 'AI 生图批次创建失败') }
  }

  const downloadAgentTasks = async () => {
    if (!batch) return
    const pending = await api.getPendingImageGenerationRequests(projectId, batch.batchId)
    const blob = new Blob([JSON.stringify(pending, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${batch.batchId}-pending-scenes.json`; anchor.click(); URL.revokeObjectURL(url)
  }

  const approve = async () => {
    if (!batch) return
    const selections = Object.entries(selectedCandidates).map(([sceneId, candidateId]) => ({ sceneId, candidateId }))
    if (!selections.length) return onMessage('没有可批准的候选图片')
    setBusy('approve')
    try {
      const result = await api.approveImageGenerationCandidates(projectId, batch.batchId, selections)
      setBatch(result.batch); await onBound(); onMessage(`已批准并绑定 ${result.bound.length} 个 Scene`)
    } catch (error: any) { onMessage(error.message || '候选绑定失败') }
    finally { setBusy('') }
  }

  const retry = async () => {
    if (!batch) return
    setBusy('retry')
    try { setBatch(await api.retryImageGenerationBatch(projectId, batch.batchId)); onMessage('失败项已重置，可以继续生成或由 Agent 回填') }
    catch (error: any) { onMessage(error.message || '没有可重试的失败项') }
    finally { setBusy('') }
  }

  return <section className="card-cinematic p-5 space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="section-index">AI IMAGE / TIMED SCENES</p><h2 className="text-xl font-heading">按配音时间生成画面</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>每张图片绑定到当前 Scene 的字幕时间窗，不改变配音与时间轴。</p></div>
      {batch && <span className="status-pill" data-tone={batch.status === 'succeeded' ? 'ok' : batch.status === 'failed' || batch.status === 'stale' ? 'danger' : 'warn'}>{batch.status} · {generatedCount}/{batch.items?.length || 0}</span>}
    </div>
    <div className="flex flex-wrap gap-2">
      <button className={channel === 'agent' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => setChannel('agent')}>Codex / Agent 生图</button>
      <button className={channel === 'local' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => setChannel('local')}>本地 Stickman（零额度）</button>
      <button className={channel === 'builtin' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => setChannel('builtin')}>外接 API 生图</button>
    </div>
    <div className="grid lg:grid-cols-2 gap-3">
      <label className="text-xs">全片视觉风格<textarea className="input-cinematic mt-1 w-full min-h-[72px]" value={styleAnchor} onChange={event => setStyleAnchor(event.target.value)} /></label>
      <label className="text-xs">人物与场景连续性<textarea className="input-cinematic mt-1 w-full min-h-[72px]" value={continuityAnchor} onChange={event => setContinuityAnchor(event.target.value)} placeholder="例如：同一位黑色风衣旅人、同一座雨夜车站" /></label>
    </div>
    {!batch && <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">{drafts.map((scene, index) => <div key={scene.sceneId} className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}>
      <div className="flex items-start gap-2"><input className="mt-1" type="checkbox" checked={scene.enabled} onChange={event => updateScene(scene.sceneId, { enabled: event.target.checked })} /><div className="flex-1"><div className="flex justify-between text-xs"><b>Scene {String(index + 1).padStart(2, '0')}</b><span style={{ color: 'var(--text-muted)' }}>{scene.start.toFixed(2)} → {scene.end.toFixed(2)}s</span></div><p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{scene.text}</p></div></div>
      <textarea className="input-cinematic w-full min-h-[76px] text-sm" value={scene.prompt} onChange={event => updateScene(scene.sceneId, { prompt: event.target.value })} placeholder="该 Scene 的最终生图 Prompt" />
      <input className="input-cinematic w-full text-xs" value={scene.negativePrompt} onChange={event => updateScene(scene.sceneId, { negativePrompt: event.target.value })} placeholder="负面 Prompt：文字、水印、Logo、畸形等" />
    </div>)}</div>}
    {channel === 'builtin' && !batch && <div className="rounded-lg border p-4 grid md:grid-cols-2 gap-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}>
      <label className="text-xs flex items-center gap-2 md:col-span-2"><input type="checkbox" checked={!!provider.enabled} onChange={event => setProvider({ ...provider, enabled: event.target.checked })} />启用 OpenAI-compatible 生图 Provider</label>
      <label className="text-xs">Base URL<input className="input-cinematic mt-1 w-full" value={provider.baseUrl} onChange={event => setProvider({ ...provider, baseUrl: event.target.value })} placeholder="https://gateway.example/v1" /></label>
      <label className="text-xs">API Key<input type="password" className="input-cinematic mt-1 w-full" value={provider.apiKey} onChange={event => setProvider({ ...provider, apiKey: event.target.value })} placeholder={provider.apiKeyConfigured ? '已配置；留空保持原 Key' : '输入 API Key'} /></label>
      <label className="text-xs">模型<input className="input-cinematic mt-1 w-full" value={provider.model} onChange={event => setProvider({ ...provider, model: event.target.value })} /></label>
      <label className="text-xs">并发数<input type="number" min="1" max="8" className="input-cinematic mt-1 w-full" value={provider.maxConcurrency} onChange={event => setProvider({ ...provider, maxConcurrency: Number(event.target.value) })} /></label>
      <div className="flex gap-2 md:col-span-2"><button className="btn-cinematic text-xs" disabled={!!busy} onClick={testProvider}><Wrench size={14} /> 测试连接</button><button className="btn-cinematic text-xs" disabled={!!busy} onClick={saveProvider}>保存到本机</button></div>
      <label className="text-xs flex items-start gap-2 md:col-span-2"><input className="mt-0.5" type="checkbox" checked={paidConfirmed} onChange={event => setPaidConfirmed(event.target.checked)} /><span>我确认本次将调用外接生图 API，可能消耗额度；预计调用 {selectedCount} 个 Scene，每 Scene {candidateCount} 张候选。</span></label>
    </div>}
    {!batch && <div className="flex flex-wrap items-end justify-between gap-3"><label className="text-xs">每 Scene 候选<select className="input-cinematic ml-2" value={candidateCount} onChange={event => setCandidateCount(Number(event.target.value))}><option value="1">1</option><option value="2">2</option><option value="4">4</option></select></label><button className="btn-gold" disabled={!!busy || !selectedCount} onClick={start}>{busy ? <Spinner className="animate-spin" size={15} /> : <Play size={15} weight="fill" />} 创建 {selectedCount} 个 Scene 生图任务</button></div>}
    {batch && <div className="space-y-3">
      {batch.channel === 'agent' && <div className="rounded-lg p-3 text-xs flex flex-wrap items-center justify-between gap-2" style={{ background: 'var(--bg-surface)' }}><span>让 Codex/MCP 读取 Batch <b>{batch.batchId}</b>，按 `finalPrompt` 逐 Scene 生图并携带原始 `inputHash` 回填。</span><button className="btn-cinematic text-xs" onClick={downloadAgentTasks}><DownloadSimple size={14} /> 下载 Agent 任务 JSON</button></div>}
      {(batch.items || []).map((item: any) => <div key={item.sceneId} className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}><div className="flex justify-between text-xs"><b>{item.sceneId}</b><span style={{ color: item.status === 'failed' ? 'var(--danger)' : 'var(--text-muted)' }}>{item.status} · {item.start.toFixed(2)}–{item.end.toFixed(2)}s</span></div><p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{item.finalPrompt}</p>{item.error && <p className="text-xs" style={{ color: 'var(--danger)' }}>{item.error}</p>}<div className="grid grid-cols-2 md:grid-cols-4 gap-2">{item.candidates?.map((candidate: any) => <button key={candidate.candidateId} className="rounded border p-1 text-[10px]" style={{ borderColor: selectedCandidates[item.sceneId] === candidate.candidateId ? 'var(--accent)' : 'var(--border-subtle)', background: 'var(--bg-surface)' }} onClick={() => setSelectedCandidates(values => ({ ...values, [item.sceneId]: candidate.candidateId }))}><img className="w-full aspect-square object-cover rounded" src={`/api/projects/${projectId}/assets/stream?path=${encodeURIComponent(candidate.path)}`} alt={`${item.sceneId} candidate`} /><span>{selectedCandidates[item.sceneId] === candidate.candidateId ? '已选择' : '候选'}</span></button>)}</div></div>)}
      <div className="flex flex-wrap justify-end gap-2"><button className="btn-cinematic text-xs" disabled={!!busy} onClick={() => refreshBatch()}><Images size={14} /> 刷新 Agent 回填</button>{batch.items?.some((item: any) => item.status === 'failed') && <button className="btn-cinematic text-xs" disabled={!!busy} onClick={retry}>只重试失败项</button>}<button className="btn-gold text-xs" disabled={!!busy || !Object.keys(selectedCandidates).length} onClick={approve}>{busy === 'approve' ? <Spinner className="animate-spin" size={14} /> : <CheckCircle size={14} weight="fill" />} 批准并绑定候选</button></div>
    </div>}
  </section>
}

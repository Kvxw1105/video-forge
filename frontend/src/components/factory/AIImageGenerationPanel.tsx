import { useEffect, useState } from 'react'
import { CheckCircle, DownloadSimple, Images, Play, Spinner, Wrench } from '@phosphor-icons/react'
import { api } from '../../lib/api'

type RouteOverride = 'auto' | 'stickman' | 'code_visual'
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
type SceneDraft = SceneInput & { enabled: boolean; providerOverride: RouteOverride }
type Props = { projectId: string; scenes: SceneInput[]; onBound: () => Promise<void> | void; onMessage: (message: string) => void }

const batchStorageKey = (projectId: string) => `videoforge:image-batch:${projectId}`
const blankProvider = { enabled: false, providerId: 'openai-compatible', baseUrl: '', apiKey: '', apiKeyConfigured: false, model: '', timeoutSeconds: 120, maxConcurrency: 4 }

export default function AIImageGenerationPanel({ projectId, scenes, onBound, onMessage }: Props) {
  const [channel, setChannel] = useState<'builtin' | 'agent' | 'local'>('local')
  const [routingMode, setRoutingMode] = useState<RouteOverride>('auto')
  const [drafts, setDrafts] = useState<SceneDraft[]>([])
  const [provider, setProvider] = useState<any>(blankProvider)
  const [styleAnchor, setStyleAnchor] = useState('cinematic, low-saturation, warm mid-century color palette')
  const [continuityAnchor, setContinuityAnchor] = useState('')
  const [candidateCount, setCandidateCount] = useState(1)
  const [paidConfirmed, setPaidConfirmed] = useState(false)
  const [codeVisualMotion, setCodeVisualMotion] = useState(true)
  const [batch, setBatch] = useState<any>(null)
  const [selectedCandidates, setSelectedCandidates] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState('')

  useEffect(() => {
    setDrafts(scenes.map(scene => ({ ...scene, enabled: Boolean(scene.prompt?.trim() || scene.text?.trim()), providerOverride: 'auto' })))
  }, [scenes])

  useEffect(() => {
    api.getAIImageProviderSettings().then(setProvider).catch(() => onMessage('外部图像 Provider 设置读取失败'))
    const remembered = localStorage.getItem(batchStorageKey(projectId))
    if (remembered) api.getImageGenerationBatch(projectId, remembered).then(setBatch).catch(() => localStorage.removeItem(batchStorageKey(projectId)))
  }, [projectId, onMessage])

  useEffect(() => {
    const next: Record<string, string> = {}
    for (const item of batch?.items || []) {
      const candidate = item.candidates?.find((value: any) => value.status === 'selected') || item.candidates?.[0]
      if (candidate) next[item.sceneId] = candidate.candidateId
    }
    setSelectedCandidates(next)
  }, [batch])

  const selectedCount = drafts.filter(scene => scene.enabled).length
  const generatedCount = (batch?.items || []).filter((item: any) => item.candidates?.length).length
  const updateScene = (sceneId: string, patch: Partial<SceneDraft>) => setDrafts(values => values.map(value => value.sceneId === sceneId ? { ...value, ...patch } : value))

  const refreshBatch = async (batchId = batch?.batchId) => {
    if (!batchId) return null
    const next = await api.getImageGenerationBatch(projectId, batchId)
    setBatch(next)
    return next
  }

  const pollJob = async (jobId: string, batchId: string) => {
    const tick = async (): Promise<void> => {
      const job = await api.getJob(jobId)
      await refreshBatch(batchId)
      if (job.status === 'queued' || job.status === 'running') {
        await new Promise(resolve => window.setTimeout(resolve, 700))
        return tick()
      }
      setBusy('')
      onMessage(job.status === 'succeeded' ? '视觉候选已生成，请选择并批准' : (job.error || '视觉生成任务失败'))
    }
    await tick()
  }

  const start = async (onlySceneId?: string, onlyMissing = false) => {
    const existing = new Set((batch?.items || []).filter((item: any) => item.candidates?.length).map((item: any) => item.sceneId))
    const target = drafts.filter(scene => scene.enabled && (!onlySceneId || scene.sceneId === onlySceneId) && (!onlyMissing || !existing.has(scene.sceneId)))
    if (!target.length) return onMessage(onlyMissing ? '当前没有缺失视觉的 Scene' : '请至少选择一个 Scene')
    if (channel === 'builtin' && !paidConfirmed) return onMessage('请先确认本次会调用外部图像 API')
    setBusy('create')
    try {
      if (channel === 'builtin') await api.updateAIImageProviderSettings(provider)
      const sceneOverrides = Object.fromEntries(target.map(scene => [scene.sceneId, {
        prompt: scene.prompt,
        negativePrompt: scene.negativePrompt,
        providerId: scene.providerOverride === 'auto' ? undefined : scene.providerOverride,
        outputMode: channel === 'local' && codeVisualMotion ? 'video' : 'static',
      }]))
      const created = await api.createImageGenerationBatch(projectId, {
        channel,
        providerId: channel === 'agent' ? 'codex-imagegen' : channel === 'local' ? routingMode : provider.providerId,
        model: channel === 'builtin' ? provider.model : '',
        routingMode,
        candidateCount,
        styleAnchor,
        continuityAnchor,
        sceneIds: target.map(scene => scene.sceneId),
        sceneOverrides,
      })
      setBatch(created)
      localStorage.setItem(batchStorageKey(projectId), created.batchId)
      if (channel === 'agent') {
        setBusy('')
        onMessage(`Agent 任务已创建：${created.items.length} 个 Scene`)
      } else {
        const result = await api.runImageGenerationBatch(projectId, created.batchId)
        setBusy('generate')
        await pollJob(result.job.jobId, created.batchId)
      }
    } catch (error: any) {
      setBusy('')
      onMessage(error.message || '视觉生成批次创建失败')
    }
  }

  const approve = async () => {
    if (!batch) return
    const selections = Object.entries(selectedCandidates).map(([sceneId, candidateId]) => ({ sceneId, candidateId }))
    if (!selections.length) return onMessage('没有可批准的候选')
    setBusy('approve')
    try {
      const result = await api.approveImageGenerationCandidates(projectId, batch.batchId, selections)
      setBatch(result.batch)
      await onBound()
      onMessage(`已批准并绑定 ${result.bound.length} 个 Scene`)
    } catch (error: any) {
      onMessage(error.message || '候选绑定失败')
    } finally {
      setBusy('')
    }
  }

  const retry = async () => {
    if (!batch) return
    setBusy('retry')
    try { setBatch(await api.retryImageGenerationBatch(projectId, batch.batchId)); onMessage('失败项已重置，可以继续生成') }
    catch (error: any) { onMessage(error.message || '没有可重试的失败项') }
    finally { setBusy('') }
  }

  const downloadAgentTasks = async () => {
    if (!batch) return
    const pending = await api.getPendingImageGenerationRequests(projectId, batch.batchId)
    const url = URL.createObjectURL(new Blob([JSON.stringify(pending, null, 2)], { type: 'application/json' }))
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `${batch.batchId}-pending-scenes.json`; anchor.click(); URL.revokeObjectURL(url)
  }

  return <section className="card-cinematic p-5 space-y-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="section-index">VISUAL PRODUCTION / TIMED SCENES</p><h2 className="text-xl font-heading">按配音时间生成视觉素材</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>Provider 只生成候选，Scene timing 与 canonical timeline 始终由项目拥有。</p></div>
      {batch && <span className="status-pill" data-tone={batch.status === 'succeeded' ? 'ok' : batch.status === 'failed' || batch.status === 'stale' ? 'danger' : 'warn'}>{batch.status} · {generatedCount}/{batch.items?.length || 0}</span>}
    </div>
    <div className="flex flex-wrap gap-2">
      <button className={channel === 'agent' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => setChannel('agent')}>Codex / Agent</button>
      <button className={channel === 'local' && routingMode === 'auto' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => { setChannel('local'); setRoutingMode('auto') }}>Auto 路由</button>
      <button className={channel === 'local' && routingMode === 'stickman' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => { setChannel('local'); setRoutingMode('stickman') }}>本地 Stickman</button>
      <button className={channel === 'local' && routingMode === 'code_visual' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => { setChannel('local'); setRoutingMode('code_visual') }}>Code Visual</button>
      <button className={channel === 'builtin' ? 'btn-gold text-xs' : 'btn-cinematic text-xs'} onClick={() => setChannel('builtin')}>外接 API</button>
    </div>
    {channel === 'local' && <div className="rounded-lg p-3 text-xs flex flex-wrap items-center justify-between gap-3" style={{ background: 'var(--bg-surface)' }}><span>当前路由：<b>{routingMode === 'auto' ? 'Auto' : routingMode === 'stickman' ? 'Stickman' : 'Code Visual'}</b> · 本地零额度</span><label className="flex items-center gap-2"><input type="checkbox" checked={codeVisualMotion} onChange={event => setCodeVisualMotion(event.target.checked)} />Code Visual 优先生成动态 MP4</label></div>}
    <div className="grid lg:grid-cols-2 gap-3"><label className="text-xs">全片视觉风格<textarea className="input-cinematic mt-1 w-full min-h-[72px]" value={styleAnchor} onChange={event => setStyleAnchor(event.target.value)} /></label><label className="text-xs">连续性锚点<textarea className="input-cinematic mt-1 w-full min-h-[72px]" value={continuityAnchor} onChange={event => setContinuityAnchor(event.target.value)} placeholder="同一角色、场景或色彩语言" /></label></div>
    {!batch && <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">{drafts.map((scene, index) => <div key={scene.sceneId} className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}><div className="flex items-start gap-2"><input className="mt-1" type="checkbox" checked={scene.enabled} onChange={event => updateScene(scene.sceneId, { enabled: event.target.checked })} /><div className="flex-1"><div className="flex justify-between text-xs"><b>Scene {String(index + 1).padStart(2, '0')}</b><span style={{ color: 'var(--text-muted)' }}>{scene.start.toFixed(2)}–{scene.end.toFixed(2)}s</span></div><p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>{scene.text}</p></div></div><div className="flex flex-wrap items-center justify-between gap-2"><label className="text-xs">Scene 路由<select className="input-cinematic ml-2 py-1" value={scene.providerOverride} onChange={event => updateScene(scene.sceneId, { providerOverride: event.target.value as RouteOverride })}><option value="auto">Auto</option><option value="stickman">Stickman</option><option value="code_visual">Code Visual</option></select></label><span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>可覆盖自动路由</span></div><textarea className="input-cinematic w-full min-h-[76px] text-sm" value={scene.prompt} onChange={event => updateScene(scene.sceneId, { prompt: event.target.value })} placeholder="输入 Scene 的最终视觉 Prompt" /><input className="input-cinematic w-full text-xs" value={scene.negativePrompt} onChange={event => updateScene(scene.sceneId, { negativePrompt: event.target.value })} placeholder="负面 Prompt" /></div>)}</div>}
    {channel === 'builtin' && !batch && <div className="rounded-lg border p-4 grid md:grid-cols-2 gap-3" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}><label className="text-xs">Base URL<input className="input-cinematic mt-1 w-full" value={provider.baseUrl} onChange={event => setProvider({ ...provider, baseUrl: event.target.value })} /></label><label className="text-xs">API Key<input type="password" className="input-cinematic mt-1 w-full" value={provider.apiKey} onChange={event => setProvider({ ...provider, apiKey: event.target.value })} /></label><label className="text-xs">模型<input className="input-cinematic mt-1 w-full" value={provider.model} onChange={event => setProvider({ ...provider, model: event.target.value })} /></label><div className="flex items-end gap-2"><button className="btn-cinematic text-xs" disabled={!!busy} onClick={async () => { setBusy('test'); try { const result = await api.testAIImageProvider(provider); onMessage(result.message || 'Provider 连接成功') } catch (error: any) { onMessage(error.message || 'Provider 连接失败') } finally { setBusy('') } }}><Wrench size={14} /> 测试连接</button><label className="text-xs flex items-center gap-2"><input type="checkbox" checked={paidConfirmed} onChange={event => setPaidConfirmed(event.target.checked)} />确认外部额度</label></div></div>}
    {!batch && <div className="flex flex-wrap items-end justify-between gap-3"><label className="text-xs">每 Scene 候选<select className="input-cinematic ml-2" value={candidateCount} onChange={event => setCandidateCount(Number(event.target.value))}><option value="1">1</option><option value="2">2</option><option value="4">4</option></select></label><button className="btn-gold" disabled={!!busy || !selectedCount} onClick={() => start()}>{busy ? <Spinner className="animate-spin" size={15} /> : <Play size={15} weight="fill" />} 创建 {selectedCount} 个 Scene 任务</button></div>}
    {batch && <div className="space-y-3">{batch.channel === 'agent' && <div className="rounded-lg p-3 text-xs flex flex-wrap items-center justify-between gap-2" style={{ background: 'var(--bg-surface)' }}><span>Agent 待读取并回填本批次候选。</span><button className="btn-cinematic text-xs" onClick={downloadAgentTasks}><DownloadSimple size={14} /> 下载任务 JSON</button></div>}{(batch.items || []).map((item: any) => <div key={item.sceneId} className="rounded-lg border p-3 space-y-2" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}><div className="flex justify-between text-xs"><b>{item.sceneId}</b><span style={{ color: item.status === 'failed' ? 'var(--danger)' : 'var(--text-muted)' }}>{item.status} · {item.providerId || batch.providerId || 'provider'} · {Number(item.start).toFixed(2)}–{Number(item.end).toFixed(2)}s</span></div><p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{item.routingReason || 'manual provider'} · confidence {(Number(item.routingConfidence || 0) * 100).toFixed(0)}% · {item.outputMode === 'video' ? 'dynamic' : 'static'}</p><p className="text-xs" style={{ color: 'var(--text-secondary)' }}>{item.finalPrompt}</p>{item.error && <p className="text-xs" style={{ color: 'var(--danger)' }}>{item.error}</p>}<div className="grid grid-cols-2 md:grid-cols-4 gap-2">{item.candidates?.map((candidate: any) => <button key={candidate.candidateId} className="rounded border p-1 text-[10px]" style={{ borderColor: selectedCandidates[item.sceneId] === candidate.candidateId ? 'var(--accent)' : 'var(--border-subtle)', background: 'var(--bg-surface)' }} onClick={() => setSelectedCandidates(values => ({ ...values, [item.sceneId]: candidate.candidateId }))}>{candidate.mimeType === 'video/mp4' ? <video className="w-full aspect-square object-cover rounded" src={`/api/projects/${projectId}/assets/stream?path=${encodeURIComponent(candidate.path)}`} muted loop autoPlay playsInline /> : <img className="w-full aspect-square object-cover rounded" src={`/api/projects/${projectId}/assets/stream?path=${encodeURIComponent(candidate.path)}`} alt={`${item.sceneId} candidate`} />}<span>{selectedCandidates[item.sceneId] === candidate.candidateId ? '已选择' : '候选'}</span></button>)}</div><div className="flex justify-end"><button className="btn-cinematic text-[11px]" disabled={!!busy} onClick={() => { setBatch(null); void start(item.sceneId) }}>重新生成此 Scene</button></div></div>)}<div className="flex flex-wrap justify-end gap-2"><button className="btn-cinematic text-xs" disabled={!!busy} onClick={() => refreshBatch()}><Images size={14} /> 刷新 Batch</button>{batch.items?.some((item: any) => !item.candidates?.length) && <button className="btn-cinematic text-xs" disabled={!!busy} onClick={() => { setBatch(null); void start(undefined, true) }}>生成缺失视觉</button>}{batch.items?.some((item: any) => item.status === 'failed') && <button className="btn-cinematic text-xs" disabled={!!busy} onClick={retry}>重试失败项</button>}<button className="btn-gold text-xs" disabled={!!busy || !Object.keys(selectedCandidates).length} onClick={approve}>{busy === 'approve' ? <Spinner className="animate-spin" size={14} /> : <CheckCircle size={14} weight="fill" />} 批准并绑定候选</button></div></div>}
  </section>
}

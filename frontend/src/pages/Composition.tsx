import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, ArrowDown, ArrowUp, Trash, Play, Export } from '@phosphor-icons/react'
import { api } from '../lib/api'

export default function Composition() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [project, setProject] = useState<any>(null)
  const [catalog, setCatalog] = useState<any[]>([])
  const [compile, setCompile] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const load = useCallback(async () => {
    if (!id) return
    const [loaded, sources] = await Promise.all([api.getProject(id), api.getStructuredCatalog()])
    setProject(loaded); setCatalog(sources)
  }, [id])
  useEffect(() => { load().catch(error => setMessage(error.message || '加载失败')) }, [load])
  const items = project?.composition?.items || []
  const updateItems = async (next: any[]) => {
    setBusy(true)
    try { const updated = await api.updateProject(id!, { composition: { ...project.composition, items: next } }); setProject(updated); setMessage('已保存') }
    catch (error: any) { setMessage(error.message || '保存失败') } finally { setBusy(false) }
  }
  const move = (index: number, delta: number) => { const target = index + delta; if (target < 0 || target >= items.length) return; const next = [...items]; [next[index], next[target]] = [next[target], next[index]]; updateItems(next) }
  const add = (source: any, variant: any) => updateItems([...items, { id: `chapter_${Date.now()}`, sourceProjectId: source.projectId, variantId: variant.id, enabled: true, chapterTitle: source.episodeTitle || source.name, chapterCardDuration: 1, gapAfter: 0.5, metadata: {} }])
  const run = async (action: 'compile' | 'preview' | 'export') => {
    setBusy(true)
    try {
      const result = action === 'compile' ? await api.compileComposition(id!) : action === 'preview' ? await api.previewComposition(id!) : await api.exportCompositionToJianYing(id!)
      if (action === 'compile') setCompile(result)
      else if (action === 'preview') window.open(result.previewUrl, '_blank', 'noopener,noreferrer')
      setMessage(action === 'export' ? `已生成剪映草稿：${result.draftName || result.draft_name}` : '操作完成')
    } catch (error: any) { setMessage(error.message || '操作失败') } finally { setBusy(false) }
  }
  const enabledCount = useMemo(() => items.filter((item: any) => item.enabled !== false).length, [items])
  if (!project) return <div className="min-h-[100dvh] flex items-center justify-center workbench-shell">{message || '加载中…'}</div>
  return <div className="min-h-[100dvh] workbench-shell p-6"><div className="max-w-6xl mx-auto space-y-5">
    <header className="flex items-center gap-3"><button className="icon-button" onClick={() => navigate('/')} aria-label="返回"><ArrowLeft size={18} /></button><div className="flex-1"><h1 className="text-xl font-heading">{project.composition?.title || project.name}</h1><p className="text-xs" style={{ color: 'var(--text-muted)' }}>长视频 Composition · {enabledCount} 个启用章节</p></div><button className="btn-cinematic" onClick={() => run('compile')} disabled={busy}><Play size={15} /> 编译检查</button><button className="btn-cinematic" onClick={() => run('preview')} disabled={busy}><Play size={15} /> 生成预览</button><button className="btn-gold" onClick={() => run('export')} disabled={busy}><Export size={15} /> 导出剪映</button></header>
    {message && <div className="status-pill" data-tone="warn">{message}</div>}
    <div className="grid lg:grid-cols-[1.2fr_1fr] gap-5"><section className="space-y-3"><div className="flex justify-between items-center"><h2 className="label-cinematic">章节列表</h2><span className="text-xs" style={{ color: 'var(--text-muted)' }}>{items.length} items</span></div>{items.map((item: any, index: number) => <div key={item.id} className="card-cinematic p-4 space-y-3"><div className="flex items-center gap-2"><span className="font-mono text-xs">{String(index + 1).padStart(2, '0')}</span><strong className="text-sm flex-1">{item.chapterTitle || '未命名章节'}</strong><button className="icon-button" onClick={() => move(index, -1)} disabled={index === 0 || busy} aria-label="上移"><ArrowUp size={15} /></button><button className="icon-button" onClick={() => move(index, 1)} disabled={index === items.length - 1 || busy} aria-label="下移"><ArrowDown size={15} /></button><button className="icon-button" onClick={() => updateItems(items.filter((_: any, i: number) => i !== index))} disabled={busy} aria-label="删除"><Trash size={15} /></button></div><div className="grid grid-cols-3 gap-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}><span>{item.sourceProjectId}</span><span>{item.variantId}</span><label className="flex gap-1"><input type="checkbox" checked={item.enabled !== false} onChange={event => updateItems(items.map((x: any, i: number) => i === index ? { ...x, enabled: event.target.checked } : x))} /> 启用</label></div><div className="grid grid-cols-2 gap-2"><label className="text-[10px]">章节卡时长<input className="input-cinematic w-full" type="number" min="0" step="0.1" value={item.chapterCardDuration || 0} onChange={event => updateItems(items.map((x: any, i: number) => i === index ? { ...x, chapterCardDuration: Number(event.target.value) } : x))} /></label><label className="text-[10px]">章节后间隔<input className="input-cinematic w-full" type="number" min="0" step="0.1" value={item.gapAfter || 0} onChange={event => updateItems(items.map((x: any, i: number) => i === index ? { ...x, gapAfter: Number(event.target.value) } : x))} /></label></div></div>)}</section><aside className="space-y-4"><div className="card-cinematic p-4"><h2 className="label-cinematic mb-3">Structured 来源</h2>{catalog.map(source => <div key={source.projectId} className="border-b py-3 last:border-0" style={{ borderColor: 'var(--border-subtle)' }}><div className="text-sm">{source.name}</div><div className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{source.episodeTitle} · {source.hasAlignment ? '已对齐' : '手动绑定'}</div><div className="flex flex-wrap gap-2 mt-2">{source.variants.map((variant: any) => <button key={variant.id} className="btn-cinematic text-[10px] py-1.5" onClick={() => add(source, variant)} disabled={busy}>添加 {variant.name || variant.id}</button>)}</div></div>)}</div>{compile && <div className="card-cinematic p-4 space-y-2"><h2 className="label-cinematic">编译结果</h2><div className="grid grid-cols-2 text-xs" style={{ color: 'var(--text-secondary)' }}><span>时长 {compile.duration.toFixed(1)}s</span><span>章节 {compile.itemCount}</span><span>画面 {compile.visualClipCount}</span><span>字幕 {compile.subtitleCount}</span><span>配音 {compile.voiceoverClipCount}</span></div>{compile.warnings?.map((warning: string) => <p key={warning} className="text-[10px]" style={{ color: 'var(--warning)' }}>{warning}</p>)}</div>}</aside></div>
  </div></div>
}

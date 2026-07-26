import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, ClipboardText, MagicWand, Plus, Scissors, Trash } from '@phosphor-icons/react'
import { api } from '../lib/api'

const TYPES = ['HOOK', 'CTA_TAG', 'PROBLEM', 'STORY', 'MECHANISM', 'JUDGMENT', 'METHOD', 'SHORT_OUTRO', 'BRIDGE_IN', 'BRIDGE_OUT', 'COMMENT_CTA']
const GRANULARITY = [
  { id: 'coarse', label: '粗：按大段', hint: '每个 Block 约 1-2 个画面' },
  { id: 'standard', label: '标准：按语义', hint: '每 2-3 句或一个小逻辑一个画面' },
  { id: 'fine', label: '细：按句子', hint: '每 1-2 句一个画面' },
  { id: 'custom', label: '自定义', hint: '指定每个画面覆盖几句或几秒' },
]
const EXAMPLE = '有些人看起来一直很冷静，但真正让他们疲惫的不是事情多，而是每一次都先压下自己的感受。今天我们拆开看看，这种习惯是怎么形成的，又怎样开始松动。'

export default function StructuredNew() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [mode, setMode] = useState<'raw' | 'advanced'>('raw')
  const [source, setSource] = useState('')
  const [blocks, setBlocks] = useState<any[]>([])
  const [templates, setTemplates] = useState<any[]>([])
  const [agentNote, setAgentNote] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  const [variants, setVariants] = useState<any[]>([])
  const [activeVariantId, setActiveVariantId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [episodeId, setEpisodeId] = useState(`episode_${Math.random().toString(36).slice(2, 8)}`)
  const [title, setTitle] = useState('')
  const [topic, setTopic] = useState('')
  const [symbol, setSymbol] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  useEffect(() => { api.listPresentationTemplates().then(value => setTemplates(value.templates || [])).catch(() => setTemplates([])) }, [])
  const presentationFor = (type: string, existing: any = {}) => {
    const template = templates.find(item => (item.blockTypes || []).includes(type)) || templates.find(item => item.id === 'narrative_support')
    return { templateId: existing.templateId || template?.id || 'narrative_support', granularity: existing.granularity || template?.granularity || 'standard', providerPreferences: existing.providerPreferences || template?.providerPreferences, presentationStyle: existing.presentationStyle || template?.presentationMode, visualPolicy: existing.visualPolicy || (existing.unitsPerScene || existing.targetDuration ? { mode: 'fixed_units', unitsPerScene: existing.unitsPerScene, targetDuration: existing.targetDuration } : undefined) }
  }
  const normalize = (items: any[]) => items.map((block, index) => {
    const metadata = block.metadata || {}
    return { id: block.id || `block_${index + 1}`, type: block.type || 'STORY', text: block.text || '', enabled: block.enabled !== false, revision: block.revision || 1, metadata: { ...metadata, presentation: presentationFor(block.type || 'STORY', metadata.presentation || {}) }, warnings: block.warnings || [] }
  })
  const activeBlocks = useMemo(() => blocks.filter(block => block.enabled !== false && block.type && block.text.trim()), [blocks])
  const updateBlock = (index: number, change: any) => setBlocks(current => current.map((item, position) => position === index ? { ...item, ...change } : item))
  const updatePresentation = (index: number, change: any) => setBlocks(current => current.map((item, position) => {
    if (position !== index) return item
    const presentation = { ...presentationFor(item.type, item.metadata?.presentation || {}), ...change }
    const selected = templates.find(template => template.id === presentation.templateId)
    if (selected) { presentation.providerPreferences = selected.providerPreferences; presentation.presentationStyle = selected.presentationMode }
    return { ...item, metadata: { ...(item.metadata || {}), presentation } }
  }))
  const organize = async (advanced = false) => {
    setBusy(advanced ? 'parse' : 'organize'); setError('')
    try {
      const result = advanced ? await api.parseStructuredMarkdown(source) : await api.organizeRawScript(source)
      const sourceBlocks = advanced ? (result.sections || []).map((section: any) => ({ ...section, id: section.suggestedId || `block_${section.index + 1}`, type: section.detectedType || 'STORY' })) : result.blocks || []
      const next = normalize(sourceBlocks)
      setBlocks(next); setTitle(result.title || ''); setName(result.title || '未命名视频'); setAgentNote(result.summary || (advanced ? '已按结构化 Markdown 解析。' : '已整理为可编辑的视频结构。')); setWarnings(result.warnings || []); setStep(2)
    } catch (reason: any) { setError(reason.message || '整理失败。原文仍保留，可改用手动分段。') } finally { setBusy('') }
  }
  const organizeOne = async (index: number) => {
    const block = blocks[index]; setBusy(`block:${index}`); setError('')
    try { const result = await api.organizeStructuredBlock(block.text, block.type); const next = result.blocks?.[0]; if (next) updateBlock(index, { ...normalize([next])[0], id: block.id }); setAgentNote(result.summary || '已重新整理该段。') }
    catch (reason: any) { setError(reason.message || '该段整理失败，原文字未改动。') } finally { setBusy('') }
  }
  const split = (index: number) => { const parts = blocks[index].text.split(/\n\s*\n/).map((value: string) => value.trim()).filter(Boolean); if (parts.length < 2) { setError('这一段至少需要两个空行分隔的段落，才能拆分。'); return }; const block = blocks[index]; setBlocks(current => [...current.slice(0, index), ...parts.map((text: string, offset: number) => ({ ...block, id: `${block.id}_${offset + 1}`, text })), ...current.slice(index + 1)]) }
  const mergeWithPrevious = (index: number) => { if (!index) return; setBlocks(current => current.map((block, position) => position === index - 1 ? { ...block, text: `${block.text}\n\n${current[index].text}` } : block).filter((_, position) => position !== index)) }
  const resetPresets = () => { const ids = (types: string[]) => activeBlocks.filter(block => types.includes(block.type)).map(block => block.id); const next = [{ id: 'publish', name: '发布版', blockIds: ids(TYPES) }, { id: 'master', name: '主叙事版', blockIds: ids(['PROBLEM', 'STORY', 'MECHANISM', 'JUDGMENT', 'METHOD']) }, { id: 'chapter', name: '章节版', blockIds: ids(['BRIDGE_IN', 'PROBLEM', 'STORY', 'MECHANISM', 'JUDGMENT', 'METHOD', 'BRIDGE_OUT']) }]; setVariants(next); setActiveVariantId(next.find(item => item.blockIds.length)?.id || null) }
  const create = async () => { setBusy('create'); setError(''); try { const project = await api.createStructuredProject(name.trim(), { episodeId, title, topic, symbol, blocks: blocks.map(({ warnings: _warnings, ...block }) => block), variants, activeVariantId }); navigate(`/editor/${project.id}`) } catch (reason: any) { setError(reason.message || '创建失败') } finally { setBusy('') } }

  return <main className="min-h-[100dvh] workbench-shell p-4 md:p-6"><div className="max-w-5xl mx-auto space-y-5">
    <header className="flex items-center gap-3"><button className="icon-button" onClick={() => navigate('/')} aria-label="返回"><ArrowLeft size={18}/></button><div className="flex-1"><p className="section-index">SCRIPT TO VIDEO STRUCTURE</p><h1 className="text-2xl font-heading">从原文开始做视频</h1></div><span className="status-pill">步骤 {step} / 4</span></header>
    {error && <div className="operation-error">{error}</div>}
    {step === 1 && <section className="card-cinematic p-5 space-y-4"><div><h2 className="text-lg font-heading">粘贴原始文案</h2><p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>直接粘贴 txt、普通 Markdown 或未分段长文。确认前不会创建项目或生成素材。</p></div><textarea className="input-cinematic w-full min-h-[360px] text-sm" value={source} onChange={event => setSource(event.target.value)} placeholder={EXAMPLE}/><div className="flex flex-wrap items-center gap-2"><button className="btn-cinematic text-xs" onClick={() => setSource(EXAMPLE)}><ClipboardText size={15}/> 填入示例原文</button><button className="btn-cinematic text-xs ml-auto" onClick={() => setMode(mode === 'raw' ? 'advanced' : 'raw')}>{mode === 'raw' ? '高级导入：已有结构化 Markdown' : '返回原文智能整理'}</button><button className="btn-gold" disabled={!source.trim() || !!busy} onClick={() => organize(mode === 'advanced')}><MagicWand size={16}/>{busy ? '处理中...' : mode === 'raw' ? '智能整理成视频结构' : '解析结构化 Markdown'} <ArrowRight size={16}/></button></div><button className="text-xs underline" style={{ color: 'var(--text-secondary)' }} onClick={() => organize(true)}>不使用 Agent，进入手动分段</button></section>}
    {step === 2 && <section className="space-y-3"><div className="card-cinematic p-4"><h2 className="label-cinematic">检查 Blocks</h2><p className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>{agentNote || '确认每段文字、类型和呈现方式。'}</p>{warnings.length > 0 && <p className="text-[11px] mt-2" style={{ color: 'var(--warning)' }}>{warnings.join('；')}</p>}</div><div className="flex justify-between items-center"><span className="text-xs" style={{ color: 'var(--text-muted)' }}>模板决定大风格；颗粒度决定这一段会拆成多少个素材场景。</span><button className="btn-cinematic text-xs" onClick={() => setBlocks(current => [...current, ...normalize([{ id: `block_${current.length + 1}`, type: 'STORY', text: '', enabled: true }])])}><Plus size={15}/> 添加 Block</button></div>{blocks.map((block, index) => { const presentation = presentationFor(block.type, block.metadata?.presentation || {}); const options = templates.filter(template => (template.blockTypes || []).includes(block.type)); const policy = presentation.visualPolicy || {}; return <article className="card-cinematic p-4 space-y-3" key={`${block.id}_${index}`}><div className="flex flex-wrap gap-2 items-center"><select className="input-cinematic text-xs" value={block.type} onChange={event => updateBlock(index, { type: event.target.value, metadata: { ...(block.metadata || {}), presentation: presentationFor(event.target.value) } })}>{TYPES.map(type => <option key={type}>{type}</option>)}</select><code className="text-xs flex-1">{block.id}</code><span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>置信度 {Math.round(Number(block.metadata?.confidence ?? 0) * 100)}%</span><label className="text-xs"><input type="checkbox" checked={block.enabled !== false} onChange={event => updateBlock(index, { enabled: event.target.checked })}/> 启用</label><button className="icon-button" title="与上一段合并" disabled={!index} onClick={() => mergeWithPrevious(index)}>合</button><button className="icon-button" title="按空行拆分" onClick={() => split(index)}><Scissors size={14}/></button><button className="icon-button" title="删除" onClick={() => setBlocks(current => current.filter((_, position) => position !== index))}><Trash size={15}/></button></div><textarea className="input-cinematic w-full min-h-[110px] text-sm" value={block.text} onChange={event => updateBlock(index, { text: event.target.value })}/><div className="grid gap-2 rounded border p-3 sm:grid-cols-2" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-surface)' }}><label className="text-xs">这一段怎么呈现<select className="input-cinematic mt-1 w-full text-xs" value={presentation.templateId} onChange={event => updatePresentation(index, { templateId: event.target.value })}>{options.length ? options.map(template => <option value={template.id} key={template.id}>{template.name}</option>) : <option value={presentation.templateId}>{presentation.templateId}</option>}</select><span className="mt-1 block text-[10px]" style={{ color: 'var(--text-muted)' }}>{options.find(template => template.id === presentation.templateId)?.description || '可在创建项目后继续调整。'}</span></label><label className="text-xs">素材颗粒度<select className="input-cinematic mt-1 w-full text-xs" value={presentation.granularity} onChange={event => updatePresentation(index, { granularity: event.target.value })}>{GRANULARITY.map(option => <option value={option.id} key={option.id}>{option.label}</option>)}</select><span className="mt-1 block text-[10px]" style={{ color: 'var(--text-muted)' }}>{GRANULARITY.find(option => option.id === presentation.granularity)?.hint}</span></label>{presentation.granularity === 'custom' && <><label className="text-xs">每个场景覆盖几句<input className="input-cinematic mt-1 w-full text-xs" type="number" min="1" max="12" value={policy.unitsPerScene || 2} onChange={event => updatePresentation(index, { visualPolicy: { ...policy, mode: 'fixed_units', unitsPerScene: Number(event.target.value) } })}/></label><label className="text-xs">目标时长（秒）<input className="input-cinematic mt-1 w-full text-xs" type="number" min="1" max="60" value={policy.targetDuration || 7} onChange={event => updatePresentation(index, { visualPolicy: { ...policy, mode: 'fixed_units', targetDuration: Number(event.target.value) } })}/></label></>}</div><div className="flex justify-between text-[11px]" style={{ color: 'var(--text-muted)' }}><span>{block.metadata?.semantic?.visualIntent || block.metadata?.semantic?.topic || '未标注语义'}</span><button className="underline" disabled={!!busy || !block.text.trim()} onClick={() => organizeOne(index)}>{busy === `block:${index}` ? '整理中...' : '重新整理这一段'}</button></div></article>})}<div className="flex justify-end gap-2"><button className="btn-cinematic" onClick={() => setStep(1)}>返回原文</button><button className="btn-gold" disabled={!activeBlocks.length} onClick={() => { resetPresets(); setStep(3) }}>确认 Blocks <ArrowRight size={16}/></button></div></section>}
    {step === 3 && <section className="space-y-3"><div className="flex justify-between items-center"><h2 className="label-cinematic">发布版本</h2><button className="btn-cinematic text-xs" onClick={resetPresets}>重置默认版本</button></div>{variants.map((variant, index) => <div className="card-cinematic p-4 space-y-3" key={variant.id}><div className="flex gap-2"><input className="input-cinematic flex-1" value={variant.name} onChange={event => setVariants(current => current.map((item, position) => position === index ? { ...item, name: event.target.value } : item))}/><span className="text-xs self-center">{variant.blockIds.length} 段</span></div><div className="flex flex-wrap gap-2">{activeBlocks.map(block => <label className="text-xs" key={block.id}><input type="checkbox" checked={variant.blockIds.includes(block.id)} onChange={event => setVariants(current => current.map((item, position) => position === index ? { ...item, blockIds: event.target.checked ? [...item.blockIds, block.id] : item.blockIds.filter((id: string) => id !== block.id) } : item))}/> {block.id}</label>)}</div></div>)}<div className="flex justify-end gap-2"><button className="btn-cinematic" onClick={() => setStep(2)}>上一步</button><button className="btn-gold" disabled={!variants.some(item => item.blockIds.length)} onClick={() => setStep(4)}>下一步 <ArrowRight size={16}/></button></div></section>}
    {step === 4 && <section className="card-cinematic p-5 space-y-3"><h2 className="label-cinematic">确认创建项目</h2>{[['项目名称', name, setName], ['Episode ID', episodeId, setEpisodeId], ['Episode 标题', title, setTitle], ['主题', topic, setTopic], ['符号', symbol, setSymbol]].map(([label, value, setter]: any) => <label className="block text-xs" key={label}>{label}<input className="input-cinematic w-full mt-1" value={value} onChange={event => setter(event.target.value)}/></label>)}<p className="text-xs" style={{ color: 'var(--text-muted)' }}>确认后才会创建 Structured Project。配音、图片和素材生成仍由后续步骤单独启动。</p><div className="flex justify-end gap-2"><button className="btn-cinematic" onClick={() => setStep(3)}>上一步</button><button className="btn-gold" disabled={!name.trim() || !activeVariantId || !!busy} onClick={create}>{busy === 'create' ? '创建中...' : '创建 Structured Project'} <Check size={16}/></button></div></section>}
  </div></main>
}

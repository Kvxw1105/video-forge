import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft, ArrowRight, Check, ClipboardText, Plus, Trash, UploadSimple } from '@phosphor-icons/react'
import { api } from '../lib/api'

const TYPES = ['HOOK', 'CTA_TAG', 'PROBLEM', 'STORY', 'MECHANISM', 'JUDGMENT', 'METHOD', 'SHORT_OUTRO', 'BRIDGE_IN', 'BRIDGE_OUT', 'COMMENT_CTA']
const EXAMPLE = `# 我的第一集\n\n## HOOK\n这里写开头。\n\n## STORY\n这里写故事。\n\n## MECHANISM\n这里写底层机制。\n\n## JUDGMENT\n这里写判断。`

export default function StructuredNew() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [source, setSource] = useState('')
  const [parsed, setParsed] = useState<any>(null)
  const [blocks, setBlocks] = useState<any[]>([])
  const [variants, setVariants] = useState<any[]>([])
  const [activeVariantId, setActiveVariantId] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [episodeId, setEpisodeId] = useState(`episode_${Math.random().toString(36).slice(2, 8)}`)
  const [title, setTitle] = useState('')
  const [topic, setTopic] = useState('')
  const [symbol, setSymbol] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const parse = async () => {
    setBusy(true); setError('')
    try {
      const result = await api.parseStructuredMarkdown(source)
      setParsed(result); setBlocks((result.sections || []).map((s: any) => ({ ...s, type: s.detectedType || '', id: s.suggestedId || `block_${s.index + 1}`, enabled: true })))
      setTitle(result.title || ''); setName(result.title || ''); setStep(2)
    } catch (e: any) { setError(e.message || '解析失败') } finally { setBusy(false) }
  }
  const resetPresets = () => {
    const ids = (type: string[]) => blocks.filter(b => type.includes(b.type) && b.enabled !== false && b.text.trim()).map(b => b.id)
    const next = [{ id: 'publish', name: 'Publish', blockIds: ids(['HOOK', 'CTA_TAG', 'PROBLEM', 'STORY', 'MECHANISM', 'JUDGMENT', 'METHOD', 'SHORT_OUTRO', 'COMMENT_CTA']) }, { id: 'master', name: 'Master', blockIds: ids(['PROBLEM', 'STORY', 'MECHANISM', 'JUDGMENT', 'METHOD']) }, { id: 'chapter', name: 'Chapter', blockIds: ids(['BRIDGE_IN', 'PROBLEM', 'STORY', 'MECHANISM', 'JUDGMENT', 'METHOD', 'BRIDGE_OUT']) }]
    setVariants(next); setActiveVariantId(next.find(v => v.blockIds.length)?.id || null)
  }
  const create = async () => {
    setBusy(true); setError('')
    try {
      const project = await api.createStructuredProject(name.trim(), { episodeId, title, topic, symbol, blocks: blocks.map(({ sourceHeading, detectedType, suggestedId, sourceStartLine, sourceEndLine, warnings, ...b }) => ({ ...b, type: b.type || undefined })), variants, activeVariantId })
      navigate(`/editor/${project.id}`)
    } catch (e: any) { setError(e.message || '创建失败') } finally { setBusy(false) }
  }
  const canContinue = useMemo(() => blocks.length > 0 && blocks.every(b => b.type && b.text.trim()), [blocks])
  return <div className="min-h-[100dvh] workbench-shell p-6"><div className="max-w-5xl mx-auto space-y-5">
    <header className="flex items-center gap-3"><button className="icon-button" onClick={() => navigate('/')} aria-label="返回"><ArrowLeft size={18} /></button><div className="flex-1"><p className="section-index">STRUCTURED EPISODE</p><h1 className="text-2xl font-heading">创建结构化内容</h1></div><span className="status-pill">步骤 {step} / 4</span></header>
    {error && <div className="operation-error">{error}</div>}
    {step === 1 && <section className="card-cinematic p-5 space-y-4"><h2 className="label-cinematic">粘贴文案</h2><p className="text-xs" style={{ color: 'var(--text-muted)' }}>支持 Markdown 二级标题或 [HOOK] 标记；未知标题不会自动猜测。</p><textarea className="input-cinematic w-full min-h-[360px] font-mono text-sm" value={source} onChange={e => setSource(e.target.value)} placeholder={EXAMPLE} /><div className="flex gap-2"><button className="btn-cinematic" onClick={() => setSource(EXAMPLE)}><ClipboardText size={16} /> 加载示例</button><button className="btn-gold ml-auto" disabled={!source.trim() || busy} onClick={parse}>{busy ? '解析中…' : '解析文案'} <ArrowRight size={16} /></button></div></section>}
    {step === 2 && <section className="space-y-3"><div className="flex justify-between items-center"><h2 className="label-cinematic">检查 Blocks</h2><button className="btn-cinematic" onClick={() => setBlocks([...blocks, { id: `block_${blocks.length + 1}`, type: '', text: '', enabled: true }])}><Plus size={16} /> 添加 Block</button></div>{blocks.map((block, index) => <div className="card-cinematic p-4 space-y-2" key={block.id}><div className="flex gap-2 items-center"><select className="input-cinematic" value={block.type} onChange={e => setBlocks(bs => bs.map((b, i) => i === index ? { ...b, type: e.target.value } : b))}><option value="">选择类型</option>{TYPES.map(t => <option key={t}>{t}</option>)}</select><code className="text-xs flex-1">{block.id}</code><label className="text-xs"><input type="checkbox" checked={block.enabled !== false} onChange={e => setBlocks(bs => bs.map((b, i) => i === index ? { ...b, enabled: e.target.checked } : b))} /> 启用</label><button className="icon-button" onClick={() => setBlocks(bs => bs.filter((_, i) => i !== index))} aria-label="删除"><Trash size={15} /></button></div><textarea className="input-cinematic w-full min-h-[100px] text-sm" value={block.text} onChange={e => setBlocks(bs => bs.map((b, i) => i === index ? { ...b, text: e.target.value } : b))} /><div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{block.text.length} 字 {block.warnings?.length ? `· ${block.warnings.join(', ')}` : ''}</div></div>)}<div className="flex justify-end gap-2"><button className="btn-cinematic" onClick={() => setStep(1)}>上一步</button><button className="btn-gold" disabled={!canContinue} onClick={() => { resetPresets(); setStep(3) }}>下一步 <ArrowRight size={16} /></button></div></section>}
    {step === 3 && <section className="space-y-3"><div className="flex justify-between items-center"><h2 className="label-cinematic">Variants</h2><button className="btn-cinematic" onClick={resetPresets}>重置默认 Preset</button></div>{variants.map((variant, index) => <div className="card-cinematic p-4 space-y-3" key={variant.id}><div className="flex gap-2"><input className="input-cinematic flex-1" value={variant.name} onChange={e => setVariants(vs => vs.map((v, i) => i === index ? { ...v, name: e.target.value } : v))} /><span className="text-xs self-center">{variant.blockIds.length} Blocks</span></div><div className="flex flex-wrap gap-2">{blocks.map(block => <label className="text-xs" key={block.id}><input type="checkbox" checked={variant.blockIds.includes(block.id)} onChange={e => setVariants(vs => vs.map((v, i) => i === index ? { ...v, blockIds: e.target.checked ? [...v.blockIds, block.id] : v.blockIds.filter((id: string) => id !== block.id) } : v))} /> {block.id}</label>)}</div></div>)}<div className="flex justify-end gap-2"><button className="btn-cinematic" onClick={() => setStep(2)}>上一步</button><button className="btn-gold" disabled={!variants.some(v => v.blockIds.length)} onClick={() => setStep(4)}>下一步 <ArrowRight size={16} /></button></div></section>}
    {step === 4 && <section className="card-cinematic p-5 space-y-3"><h2 className="label-cinematic">项目资料</h2>{[['项目名称', name, setName], ['Episode ID', episodeId, setEpisodeId], ['Episode 标题', title, setTitle], ['主题', topic, setTopic], ['符号', symbol, setSymbol]].map(([label, value, setter]: any) => <label className="block text-xs" key={label}>{label}<input className="input-cinematic w-full mt-1" value={value} onChange={e => setter(e.target.value)} /></label>)}<p className="text-xs" style={{ color: 'var(--text-muted)' }}>共 {blocks.length} 个 Block；publish {variants.find(v => v.id === 'publish')?.blockIds.length || 0}，master {variants.find(v => v.id === 'master')?.blockIds.length || 0}，chapter {variants.find(v => v.id === 'chapter')?.blockIds.length || 0}</p><div className="flex justify-end gap-2"><button className="btn-cinematic" onClick={() => setStep(3)}>上一步</button><button className="btn-gold" disabled={!name.trim() || !activeVariantId || busy} onClick={create}>{busy ? '创建中…' : '创建 Structured Project'} <Check size={16} /></button></div></section>}
  </div></div>
}

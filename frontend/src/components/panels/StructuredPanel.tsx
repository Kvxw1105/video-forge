import { useEffect, useState } from 'react'
import { api } from '../../lib/api'

type Props = { projectId: string; structuredContent: any; onToast: (type: 'ok' | 'error', message: string) => void }

export default function StructuredPanel({ projectId, structuredContent, onToast }: Props) {
  const [status, setStatus] = useState<any>(null)
  const [referenceId, setReferenceId] = useState('')
  const [generating, setGenerating] = useState(false)
  const [busyVariant, setBusyVariant] = useState('')
  const episode = structuredContent?.episode
  const variants = episode?.variants || []
  useEffect(() => { api.getStructuredAudioStatus(projectId).then(setStatus).catch(() => setStatus(null)) }, [projectId])
  if (!episode) return null
  const generate = async () => {
    setGenerating(true)
    try {
      const result = await api.generateFishAlignedAudio(projectId, { referenceId: referenceId || undefined, generateSubtitles: true })
      setStatus((current: any) => ({ ...current, hasAlignment: true, generationId: result.generationId, blockCount: result.blockCount, subtitleCount: result.subtitleCount, overallConfidence: result.overallConfidence }))
      onToast('ok', `连续配音已生成，${result.blockCount} 个 Block 已对齐`)
    } catch (error: any) { onToast('error', error.message || 'Fish Audio 生成失败') } finally { setGenerating(false) }
  }
  const preview = async (variantId: string) => {
    setBusyVariant(variantId)
    try { const result = await api.previewStructuredVariant(projectId, variantId); window.open(result.previewUrl, '_blank', 'noopener,noreferrer') }
    catch (error: any) { onToast('error', error.message || 'Variant 预览失败') } finally { setBusyVariant('') }
  }
  const exportVariant = async (variantId: string) => {
    setBusyVariant(variantId)
    try { const result = await api.exportStructuredVariantToJianYing(projectId, variantId); onToast('ok', `已生成剪映草稿：${result.draftName || result.draft_name}`) }
    catch (error: any) { onToast('error', error.message || '剪映导出失败') } finally { setBusyVariant('') }
  }
  return <div className="space-y-4">
    <div className="card-cinematic p-4 space-y-3">
      <div className="flex items-center justify-between"><h3 className="label-cinematic">链式内容</h3><span className="status-pill" data-tone={status?.hasAlignment ? 'ok' : 'warn'}>{status?.hasAlignment ? '已对齐' : '未配音'}</span></div>
      <div className="grid grid-cols-2 gap-2 text-[11px]" style={{ color: 'var(--text-secondary)' }}><span>Block {episode.blocks?.length || 0}</span><span>字幕 {status?.subtitleCount || 0}</span><span>置信度 {status?.overallConfidence ? `${Math.round(status.overallConfidence * 100)}%` : '—'}</span><span>{status?.fishConfigured ? 'Fish 已配置' : 'Fish 未配置'}</span></div>
      <button className="btn-cinematic w-full text-xs" disabled={!!status?.hasAlignment} title={status?.hasAlignment ? '当前文案已生成对齐结果，暂不允许直接编辑' : undefined}>编辑结构</button>
      <input className="input-cinematic w-full text-xs" placeholder="Reference ID（可选）" value={referenceId} onChange={event => setReferenceId(event.target.value)} />
      <button className="btn-gold w-full text-xs py-2.5" onClick={generate} disabled={generating || !status?.fishConfigured}>{generating ? '生成并对齐中…' : '生成连续主配音并自动对齐'}</button>
      {!status?.fishConfigured && <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>请先在设置中配置现有 Fish Audio 凭据。</p>}
    </div>
    <div className="space-y-2">{variants.map((variant: any) => <div key={variant.id} className="card-cinematic p-3 space-y-2"><div className="flex justify-between"><strong className="text-xs">{variant.name || variant.id}</strong><span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{variant.blockIds?.length || 0} Blocks</span></div><div className="flex gap-2"><button className="btn-cinematic flex-1 text-[11px] py-2" onClick={() => preview(variant.id)} disabled={!!busyVariant}>{busyVariant === variant.id ? '处理中…' : '预览'}</button><button className="btn-cinematic flex-1 text-[11px] py-2" onClick={() => exportVariant(variant.id)} disabled={!!busyVariant}>导出剪映</button></div></div>)}</div>
  </div>
}

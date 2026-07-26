import { useEffect, useState, type PointerEvent } from 'react'
import { api } from '../../lib/api'
import { Play, Spinner } from '@phosphor-icons/react'

type Props = { projectId: string; structuredContent: any; onToast: (type: 'ok' | 'error', message: string) => void; onRefresh?: () => Promise<any> }

export default function StructuredPanel({ projectId, structuredContent, onToast, onRefresh }: Props) {
  const [status, setStatus] = useState<any>(null)
  const [referenceId, setReferenceId] = useState('')
  const [generating, setGenerating] = useState(false)
  const [busyVariant, setBusyVariant] = useState('')
  const [visualScenes, setVisualScenes] = useState<any[]>([])
  const [rendererId, setRendererId] = useState<'mechanism_diagram' | 'white_sketch' | 'silhouette' | 'pixel_rules'>('mechanism_diagram')
  const [themeMode, setThemeMode] = useState<'light' | 'dark'>('light')
  const [overlayX, setOverlayX] = useState(0.5)
  const [overlayY, setOverlayY] = useState(0.32)
  const [overlayScale, setOverlayScale] = useState(0.36)
  const [overlayDurationPolicy, setOverlayDurationPolicy] = useState<'loop' | 'freeze_last_frame' | 'trim'>('loop')
  const [transparentVideo, setTransparentVideo] = useState(false)
  const [draggingOverlay, setDraggingOverlay] = useState(false)
  const [busyScene, setBusyScene] = useState('')
  const [recommendations, setRecommendations] = useState<Record<string, any>>({})
  const episode = structuredContent?.episode
  const variants = episode?.variants || []
  useEffect(() => { api.getStructuredAudioStatus(projectId).then(setStatus).catch(() => setStatus(null)) }, [projectId])
  useEffect(() => { api.getVisualPlan(projectId).then(value => setVisualScenes(value?.scenes || value?.visualPlan?.scenes || [])).catch(() => setVisualScenes([])) }, [projectId])
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
  const proposeVisuals = async () => {
    try { const proposal = await api.proposeVisualPlan(projectId); const plan = { planId: `plan_${Date.now()}`, sourceHash: proposal.sourceHash, scenes: proposal.scenes, settings: proposal.settings }; await api.saveVisualPlan(projectId, plan); setVisualScenes(proposal.scenes); onToast('ok', `已建立 ${proposal.scenes.length} 个视觉分镜`) }
    catch (error: any) { onToast('error', error.message || '视觉分镜规划失败') }
  }
  const exportPack = async () => { try { const result = await api.exportVisualPack(projectId); onToast('ok', `已导出生成包：${result.path}`) } catch (error: any) { onToast('error', error.message || '生成包导出失败') } }
  const validateVisuals = async () => { try { const result = await api.validateVisualPlan(projectId); onToast(result.valid ? 'ok' : 'error', result.valid ? '视觉分镜验证通过' : (result.errors || []).join('; ')) } catch (error: any) { onToast('error', error.message || '视觉分镜验证失败') } }
  const recommendOverlays = async () => { try { const result = await api.recommendCodeVisualOverlays(projectId, visualScenes.map(scene => scene.id)); setRecommendations(Object.fromEntries(result.recommendations.map(item => [item.sceneId, item]))); onToast('ok', `已为 ${result.recommendations.length} 个 Scene 给出画中画推荐`) } catch (error: any) { onToast('error', error.message || '画中画推荐失败') } }
  const renderOverlay = async (scene: any) => {
    setBusyScene(scene.id)
    try {
      const result = await api.renderCodeVisualOverlay(projectId, scene.id, { rendererId, themeMode, overlayX, overlayY, overlayScale, overlayDurationPolicy, exportTransparentVideo: transparentVideo })
      await onRefresh?.()
      setVisualScenes(current => current.map(item => item.id === scene.id ? { ...item, metadata: { ...(item.metadata || {}), videoOverlayIds: result.bindings?.map((binding: any) => binding.assetId) || [] } } : item))
      onToast('ok', `Scene ${scene.id} 已生成代码视觉画中画，可点击预览查看`)
    } catch (error: any) { onToast('error', error.message || '代码视觉画中画生成失败') } finally { setBusyScene('') }
  }
  const updateOverlayPosition = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect()
    setOverlayX(Math.min(1, Math.max(0, Number(((event.clientX - rect.left) / rect.width).toFixed(2)))))
    setOverlayY(Math.min(1, Math.max(0, Number(((event.clientY - rect.top) / rect.height).toFixed(2)))))
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
    <div className="card-cinematic p-4 space-y-2">
      <div className="flex justify-between items-center"><h3 className="label-cinematic">Visual scenes</h3><span className="text-[10px]">{visualScenes.length} Scenes</span></div>
      <div className="flex gap-2"><button className="btn-cinematic flex-1 text-[11px] py-2" onClick={proposeVisuals}>Propose</button><button className="btn-cinematic flex-1 text-[11px] py-2" onClick={validateVisuals} disabled={visualScenes.length === 0}>Validate</button><button className="btn-cinematic flex-1 text-[11px] py-2" onClick={exportPack} disabled={visualScenes.length === 0}>Export pack</button></div>
      <div className="border-t pt-3 space-y-2" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center justify-between"><h4 className="text-xs font-heading">代码视觉画中画</h4><span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>背景保持主轨</span></div>
        <button className="btn-cinematic w-full text-[11px] py-2" onClick={recommendOverlays} disabled={visualScenes.length === 0}>自动推荐样式与位置</button>
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <label>样式<select className="input-cinematic w-full mt-1" value={rendererId} onChange={event => setRendererId(event.target.value as typeof rendererId)}><option value="mechanism_diagram">机制图</option><option value="white_sketch">白板手绘</option><option value="silhouette">剪影</option><option value="pixel_rules">像素规则</option></select></label>
          <label>主题<select className="input-cinematic w-full mt-1" value={themeMode} onChange={event => setThemeMode(event.target.value as typeof themeMode)}><option value="light">浅色</option><option value="dark">深色</option></select></label>
          <label>水平位置<input className="input-cinematic w-full mt-1" type="number" min="0" max="1" step="0.01" value={overlayX} onChange={event => setOverlayX(Number(event.target.value))} /></label>
          <label>垂直位置<input className="input-cinematic w-full mt-1" type="number" min="0" max="1" step="0.01" value={overlayY} onChange={event => setOverlayY(Number(event.target.value))} /></label>
          <label>缩放<input className="input-cinematic w-full mt-1" type="number" min="0.05" max="1" step="0.01" value={overlayScale} onChange={event => setOverlayScale(Number(event.target.value))} /></label>
          <label>时长不足<select className="input-cinematic w-full mt-1" value={overlayDurationPolicy} onChange={event => setOverlayDurationPolicy(event.target.value as typeof overlayDurationPolicy)}><option value="loop">循环</option><option value="freeze_last_frame">停在最后一帧</option><option value="trim">裁切</option></select></label>
          <label className="flex items-center gap-2 pt-5"><input type="checkbox" checked={transparentVideo} onChange={event => setTransparentVideo(event.target.checked)} />导出透明 PNG 序列</label>
        </div>
        <div
          className="relative mx-auto mt-2 h-32 w-24 touch-none overflow-hidden border"
          style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border)', cursor: draggingOverlay ? 'grabbing' : 'crosshair' }}
          onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); setDraggingOverlay(true); updateOverlayPosition(event) }}
          onPointerMove={event => { if (draggingOverlay) updateOverlayPosition(event) }}
          onPointerUp={() => setDraggingOverlay(false)}
          onPointerCancel={() => setDraggingOverlay(false)}
          title="拖动小窗位置"
        >
          <span className="absolute border" style={{ left: `${overlayX * 100}%`, top: `${overlayY * 100}%`, width: `${overlayScale * 100}%`, aspectRatio: '1 / 1', transform: 'translate(-50%, -50%)', borderColor: 'var(--accent)', background: 'color-mix(in srgb, var(--accent) 18%, transparent)' }} />
          <span className="absolute bottom-1 left-0 right-0 text-center text-[9px]" style={{ color: 'var(--text-muted)' }}>拖动调整位置</span>
        </div>
      </div>
      {visualScenes.map((scene: any) => <div key={scene.id} className="text-[11px] space-y-2 border-t pt-3" style={{ borderColor: 'var(--border-subtle)' }}><div>{scene.id} / {scene.blockId} / {scene.subtitleIds?.length || 0} subtitles</div><div style={{ color: 'var(--text-muted)' }}>{scene.summary || scene.prompt || 'No prompt'} · {scene.requestedMediaType || 'image'} · {(scene.visualAssetIds || []).length ? `${scene.visualAssetIds.length} asset(s)` : 'missing asset'}</div>{recommendations[scene.id] && <div className="text-[10px]" style={{ color: 'var(--accent)' }}>推荐：{recommendations[scene.id].rendererId} · {recommendations[scene.id].reason}</div>}<button className="btn-gold w-full text-[11px] py-2 flex items-center justify-center gap-1.5" onClick={() => renderOverlay(scene)} disabled={!!busyScene}><>{busyScene === scene.id ? <Spinner size={13} className="animate-spin" /> : <Play size={13} weight="fill" />} {busyScene === scene.id ? '生成画中画中...' : '生成代码视觉画中画'}</></button></div>)}
    </div>
  </div>
}

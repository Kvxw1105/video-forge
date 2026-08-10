import { ChangeEvent, DragEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, Check, Copy, FileArrowDown, FolderOpen, Pause, Play, Trash, UploadSimple, WarningCircle } from '@phosphor-icons/react'
import { api } from '../lib/api'
import AIImageGenerationPanel from '../components/factory/AIImageGenerationPanel'

const seconds = (value: number) => `${String(Math.floor(value / 60)).padStart(2, '0')}:${(value % 60).toFixed(3).padStart(6, '0')}`

export default function FactoryVisualPairing() {
  const { batchId = '', itemId = '' } = useParams()
  const navigate = useNavigate()
  const audio = useRef<HTMLAudioElement | null>(null)
  const [data, setData] = useState<any>(null)
  const [selected, setSelected] = useState<string>('')
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState<string>('')
  const [unassigned, setUnassigned] = useState<File[]>([])
  const load = useCallback(async () => {
    if (!batchId || !itemId) return
    const value = await api.getFactoryItemVisuals(batchId, itemId)
    setData(value); setSelected(current => current || value.scenes?.[0]?.sceneId || '')
  }, [batchId, itemId])
  useEffect(() => { load().catch((error: any) => setMessage(error.message || '加载配对台失败')) }, [load])
  useEffect(() => () => { audio.current?.pause() }, [])
  const scene = useMemo(() => data?.scenes?.find((value: any) => value.sceneId === selected) || data?.scenes?.[0], [data, selected])
  const complete = Boolean(data?.coverage?.complete)
  const bind = async (target: any, file: File, replace = false) => {
    setBusy(target.sceneId)
    try { await api.uploadFactorySceneVisual(batchId, itemId, target.sceneId, file, replace); setMessage(`已绑定到 Scene ${String(target.sceneIndex).padStart(2, '0')}`); await load() }
    catch (error: any) { setMessage(error.message || '绑定失败') } finally { setBusy('') }
  }
  const choose = (target: any, event: ChangeEvent<HTMLInputElement>) => { const file = event.target.files?.[0]; if (file) bind(target, file, Boolean(target.boundAsset)); event.target.value = '' }
  const drop = (target: any, event: DragEvent) => { event.preventDefault(); const file = event.dataTransfer.files?.[0]; if (file) bind(target, file, Boolean(target.boundAsset)) }
  const play = (target: any) => {
    if (!audio.current || !data?.audio?.url) return
    audio.current.pause(); audio.current.currentTime = target.audioStart; audio.current.play().catch(() => setMessage('音频加载或播放失败'))
    audio.current.ontimeupdate = () => { if (audio.current && audio.current.currentTime >= target.audioEnd) audio.current.pause() }
  }
  const importBatch = async (files: FileList | null) => {
    if (!files || !data) return
    const left: File[] = []
    for (const file of Array.from(files)) {
      const lower = file.name.toLowerCase()
      const matches = data.scenes.filter((target: any) => lower.startsWith(target.sceneId.toLowerCase()) || lower === target.expectedFilename.toLowerCase() || lower.startsWith(target.expectedFilename.replace(/\.[^.]+$/, '').toLowerCase() + '_'))
      if (matches.length === 1) await bind(matches[0], file, Boolean(matches[0].boundAsset)); else left.push(file)
    }
    setUnassigned(left)
    if (left.length) setMessage(`${left.length} 个文件未自动匹配，请在对应 Scene 中手动选择文件`)
  }
  const unbind = async (target: any) => { if (!confirm('解除此 Scene 的素材绑定？')) return; setBusy(target.sceneId); try { await api.unbindFactorySceneVisual(batchId, itemId, target.sceneId, true); await load() } catch (error: any) { setMessage(error.message || '解绑失败') } finally { setBusy('') } }
  const resume = async () => { setBusy('resume'); try { await api.validateFactoryItemVisuals(batchId, itemId); const value = await api.resumeFactoryItem(batchId, itemId); setMessage(value.reused ? '已有输出仍可复用' : 'Preview 和剪映草稿已开始生成'); await load() } catch (error: any) { setMessage(error.message || '当前不能生成') } finally { setBusy('') } }
  const download = () => {
    const rows = data?.scenes?.map((value: any) => ({ sceneIndex: value.sceneIndex, sceneId: value.sceneId, start: value.start, end: value.end, duration: value.duration, text: value.text, prompt: value.prompt, negativePrompt: value.negativePrompt, requestedMediaType: value.requestedMediaType, expectedFilename: value.expectedFilename })) || []
    const blob = new Blob([JSON.stringify(rows, null, 2)], { type: 'application/json' }); const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = 'scene-material-list.json'; a.click(); URL.revokeObjectURL(url)
  }
  if (!data) return <main className="min-h-[100dvh] workbench-shell grid place-items-center">{message || '正在加载配对台…'}</main>
  const bound = data.coverage?.boundScenes || 0
  return <main className="min-h-[100dvh] workbench-shell p-4 md:p-6"><div className="max-w-7xl mx-auto space-y-4">
    <header className="card-cinematic p-4 flex flex-wrap gap-3 items-center"><button className="icon-button" onClick={() => navigate('/')} aria-label="返回"><ArrowLeft size={18} /></button><div className="flex-1 min-w-[220px]"><h1 className="text-lg font-heading">素材配对台 · {data.itemName}</h1><p className="text-xs" style={{ color: 'var(--text-muted)' }}>Batch {batchId} · {data.status}</p></div><div className="text-xs grid grid-cols-2 gap-x-4" style={{ color: 'var(--text-secondary)' }}><span>Scene {bound} / {data.coverage?.totalScenes}</span><span>缺少 {data.coverage?.missingScenes?.length || 0}</span><span>录音 {data.audio?.duration?.toFixed?.(1) || 0}s</span><span>{complete ? '素材齐全' : '等待素材'}</span></div><label className="btn-cinematic text-xs cursor-pointer"><UploadSimple size={15} /> 批量导入<input hidden type="file" multiple accept="image/*,video/*" onChange={event => importBatch(event.target.files)} /></label><button className="btn-cinematic text-xs" onClick={download}><FileArrowDown size={15} /> 素材清单</button><button className="btn-gold text-xs" disabled={!complete || busy === 'resume'} title={!complete ? '请先完成所有 Scene 绑定' : ''} onClick={resume}><Play size={15} /> 生成 Preview 与剪映草稿</button></header>
    {message && <div className="status-pill" data-tone="warn">{message}</div>}
    <audio ref={audio} src={data.audio?.url || undefined} preload="metadata" />
    <div className="grid xl:grid-cols-[240px_minmax(0,1fr)_300px] gap-4">
      <aside className="card-cinematic p-3 space-y-2"><div className="label-cinematic">Scene 时间线</div>{data.scenes.map((value: any) => <button key={value.sceneId} onClick={() => setSelected(value.sceneId)} className="w-full text-left p-3 rounded-lg border transition-colors" style={{ borderColor: selected === value.sceneId ? 'var(--accent)' : 'var(--border-subtle)', background: selected === value.sceneId ? 'var(--bg-elevated)' : 'var(--bg-surface)' }}><div className="flex justify-between text-xs"><strong>Scene {String(value.sceneIndex).padStart(2, '0')}</strong>{value.boundAsset ? <Check size={15} /> : <WarningCircle size={15} />}</div><div className="text-[10px] mt-1" style={{ color: 'var(--text-muted)' }}>{seconds(value.start)} → {seconds(value.end)}</div></button>)}</aside>
      {scene && <section className="card-cinematic p-5 space-y-4"><div className="flex flex-wrap justify-between gap-3"><div><div className="label-cinematic">Scene {String(scene.sceneIndex).padStart(2, '0')}</div><div className="text-sm mt-1">{seconds(scene.start)} → {seconds(scene.end)} · {scene.duration.toFixed(2)} 秒</div></div><div className="flex gap-2"><button className="btn-cinematic text-xs" onClick={() => play(scene)}><Play size={14} /> 播放本段</button><button className="btn-cinematic text-xs" onClick={() => audio.current?.pause()}><Pause size={14} /> 暂停</button></div></div><div className="rounded-lg p-4" style={{ background: 'var(--bg-elevated)' }}><p className="text-sm leading-7">{scene.text || '此 Scene 没有字幕文本。'}</p><p className="text-[11px] mt-2" style={{ color: 'var(--text-muted)' }}>Block：{scene.blockId} · 推荐：{scene.requestedMediaType} · 预计文件：{scene.expectedFilename}</p></div><div className="grid md:grid-cols-2 gap-3 text-xs"><div><b>提示词</b><p className="mt-1 break-words" style={{ color: 'var(--text-secondary)' }}>{scene.prompt || '尚未填写提示词'}</p></div><div><b>负面提示词</b><p className="mt-1 break-words" style={{ color: 'var(--text-secondary)' }}>{scene.negativePrompt || '无'}</p></div></div><div className="flex gap-2"><button className="btn-cinematic text-xs" onClick={() => navigator.clipboard.writeText(scene.prompt || '').then(() => setMessage('提示词已复制'))}><Copy size={14} /> 复制提示词</button><label className="btn-gold text-xs cursor-pointer"><FolderOpen size={14} /> {scene.boundAsset ? '更换素材' : '选择文件'}<input hidden type="file" accept="image/*,video/*" onChange={event => choose(scene, event)} /></label>{scene.boundAsset && <button className="btn-cinematic text-xs" onClick={() => unbind(scene)} disabled={busy === scene.sceneId}><Trash size={14} /> 解除绑定</button>}</div></section>}
      <aside className="card-cinematic p-4 space-y-3"><div className="label-cinematic">当前素材</div>{scene?.boundAsset ? <><div className="rounded-lg p-3" style={{ background: 'var(--bg-elevated)' }}><div className="text-sm break-all">{scene.boundAsset.name}</div><div className="text-[11px] mt-2" style={{ color: 'var(--text-muted)' }}>{scene.boundAsset.type} · {(scene.boundAsset.size / 1024).toFixed(1)} KB</div>{scene.boundAsset.type === 'video' && <p className="text-[11px] mt-2" style={{ color: 'var(--warning)' }}>最终会放入 {scene.duration.toFixed(2)} 秒 Scene 窗口；裁切/循环效果请在 Preview 确认。</p>}</div></> : <div className="text-sm rounded-lg p-4" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>拖入或选择任意文件名的图片/视频，再显式绑定到当前 Scene。</div>}<div className="label-cinematic pt-3">待分配素材</div>{unassigned.length ? unassigned.map(file => <div key={file.name} className="text-xs p-2 rounded" style={{ background: 'var(--bg-elevated)' }}>{file.name}<div style={{ color: 'var(--text-muted)' }}>{(file.size / 1024).toFixed(1)} KB · 请在目标 Scene 选择文件</div></div>) : <p className="text-xs" style={{ color: 'var(--text-muted)' }}>没有未匹配文件。</p>}</aside>
    </div>
    <AIImageGenerationPanel projectId={data.projectId} scenes={data.scenes} onBound={load} onMessage={setMessage} />
  </div></main>
}

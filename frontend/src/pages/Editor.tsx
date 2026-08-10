import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Play, Spinner, ArrowUUpLeft, ArrowUUpRight, Images, TextAa, Sliders, Export, X } from '@phosphor-icons/react'
import { useProject } from '../hooks/useProject'
import { useProgress, LoadingProgress } from '../hooks/useProgress'
import { api } from '../lib/api'
import TopBar from '../components/layout/TopBar'
import AssetPanel from '../components/panels/AssetPanel'
import ScriptPanel from '../components/panels/ScriptPanel'
import AudioPanel from '../components/panels/AudioPanel'
import OverlayPanel from '../components/panels/OverlayPanel'
import RhythmPanel from '../components/panels/RhythmPanel'
import StructuredPanel from '../components/panels/StructuredPanel'
import CanvasPreview from '../components/canvas/CanvasPreview'
import AudioPlayer from '../components/ui/AudioPlayer'
import { RatioGroup, ScaleControl, FitControl } from '../components/toolbar/PreviewToolbar'

const RATIOS: { key: string; w: number; h: number; label: string }[] = [
  { key: '9:16', w: 1080, h: 1920, label: '竖屏 9:16' },
  { key: '16:9', w: 1920, h: 1080, label: '横屏 16:9' },
  { key: '4:3', w: 1440, h: 1080, label: '横屏 4:3' },
  { key: '1:1', w: 1080, h: 1080, label: '方形 1:1' },
  { key: '4:5', w: 1080, h: 1350, label: '4:5' },
]

function selectActiveVoiceover(audio: any) {
  const playable = (v: any) => {
    const file = String(v?.file || '').replace(/\\/g, '/').split('/').pop() || ''
    if (!file) return false
    // Reject legacy bare placeholder only (relative voiceover.mp3 with no duration/text).
    if (file === 'voiceover.mp3' && Number(v?.duration || 0) <= 0 && !String(v?.text || '').trim()) return false
    return Number(v?.duration || 0) > 0 || !!String(v?.text || '').trim()
  }
  const voiceovers = audio?.voiceovers || []
  if (voiceovers.length > 0) {
    // Multi-version mode: only active + playable; no silent inactive fallback.
    return voiceovers.find((v: any) => v.isActive && playable(v)) || null
  }
  return playable(audio?.voiceover) ? audio.voiceover : null
}

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

export default function Editor() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { project, loading, error, reload, update: rawUpdate } = useProject(id!)

  // --- Undo/Redo refs (must be before update callback) ---
  const historyRef = useRef<any[]>([])
  const historyIdxRef = useRef(-1)
  const [historyLen, setHistoryLen] = useState(0)
  const [historyPos, setHistoryPos] = useState(-1)
  const isUndoRedoRef = useRef(false)
  const historyProjectIdRef = useRef('')
  const previewProjectVersionRef = useRef('')

  const pushHistory = useCallback((snapshot: any) => {
    if (isUndoRedoRef.current) return
    const idx = historyIdxRef.current
    historyRef.current = historyRef.current.slice(0, idx + 1)
    historyRef.current.push(snapshot)
    if (historyRef.current.length > 50) historyRef.current.shift()
    historyIdxRef.current = historyRef.current.length - 1
    setHistoryLen(historyRef.current.length)
    setHistoryPos(historyIdxRef.current)
  }, [])

  const showToast = useCallback((type: 'ok' | 'error', msg: string) => {
    setToast({ type, msg })
    setTimeout(() => setToast(null), 4000)
  }, [])

  // Wrapped update: save the resulting state so both undo and redo are complete.
  const update = useCallback(async (data: any) => {
    setSaveStatus('saving')
    try {
      const updated = await rawUpdate(data)
      if (!isUndoRedoRef.current) {
        pushHistory(JSON.parse(JSON.stringify(updated)))
      }
      setSaveStatus('saved')
      return updated
    } catch (e: any) {
      const msg = e?.message || '保存失败'
      setSaveStatus('error')
      showToast('error', msg)
      throw e
    }
  }, [rawUpdate, pushHistory, showToast])

  const [generating, setGenerating] = useState(false)
  const [generated, setGenerated] = useState(false)
  const [voiceoverVersion, setVoiceoverVersion] = useState(0)
  const [activeVoiceoverId, setActiveVoiceoverId] = useState<string | null>(null)
  const [duration, setDuration] = useState(0)
  const [subtitleCount, setSubtitleCount] = useState(0)
  const [exporting, setExporting] = useState(false)
  const [syncingJianying, setSyncingJianying] = useState(false)
  const [jianyingStatus, setJianyingStatus] = useState<any>(null)
  const [toast, setToast] = useState<{ type: 'ok' | 'error'; msg: string } | null>(null)
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('saved')
  const [ttsSettings, setTtsSettings] = useState<any>(null)
  const [rendering, setRendering] = useState(false)
  const [previewUrl, setPreviewUrl] = useState('')
  const [shuffleMode, setShuffleMode] = useState(true)
  const [perImageDuration, setPerImageDuration] = useState(1.0)
  const [bgmTracks, setBgmTracks] = useState<any[]>([])
  const [cueMode, setCueMode] = useState('uniform')
  const [activeTab, setActiveTab] = useState<'script' | 'assets' | 'adjust' | 'export' | 'structured'>('script')

  useEffect(() => {
    if (!project || historyProjectIdRef.current === project.id) return
    const initial = JSON.parse(JSON.stringify(project))
    historyRef.current = [initial]
    historyIdxRef.current = 0
    historyProjectIdRef.current = project.id
    setHistoryLen(1)
    setHistoryPos(0)
  }, [project?.id])

  useEffect(() => {
    if (
      previewUrl
      && previewProjectVersionRef.current
      && project?.updated_at !== previewProjectVersionRef.current
    ) {
      previewProjectVersionRef.current = ''
      setPreviewUrl('')
    }
  }, [previewUrl, project?.updated_at])

  // Derived from project directly — no separate useState needed, avoids sync bugs on undo/redo/refresh
  const visualMode: 'single' | 'carousel' = project?.visualMode === 'carousel' ? 'carousel' : 'single'
  const projectAssets = useMemo(() => (project?.assets || []).filter((a: any) => a.type === 'image' || a.type === 'video'), [project?.assets])
  const primaryVisualSegment = useMemo(
    () => (project?.segments || []).find((segment: any) => segment.type !== 'black' && segment.assetPath) || null,
    [project?.segments]
  )
  const subtitleFontSize = project?.subtitles?.[0]?.style?.fontSize || 48
  const subtitlePosition = project?.subtitles?.[0]?.style?.position || 'bottom_center'
  const bgColor = project?.canvas?.background?.value || (document.documentElement.classList.contains('light') ? '#f5f0e8' : '#000000')
  const adjustments = project?.overlays?.adjustments || { brightness: 0, contrast: 1 }

  // Loading progress hooks
  const voiceoverProgress = useProgress()
  const exportProgress = useProgress()
  const renderProgress = useProgress()

  const waitForJob = useCallback(async <T,>(jobId: string, progress: any, fallbackLabel: string): Promise<T> => {
    while (true) {
      const job = await api.getJob<T>(jobId)
      progress.set(job.progress, job.message || fallbackLabel)
      if (job.status === 'succeeded') {
        if (!job.result) throw new Error('任务完成但没有返回结果')
        return job.result
      }
      if (job.status === 'failed') {
        throw new Error(job.error || job.message || '任务失败')
      }
      await new Promise(resolve => setTimeout(resolve, 500))
    }
  }, [])

  const handleUndo = useCallback(async () => {
    const idx = historyIdxRef.current
    if (idx <= 0) return
    const prev = historyRef.current[idx - 1]
    isUndoRedoRef.current = true
    try {
      await update(prev)
      historyIdxRef.current = idx - 1
      setHistoryPos(idx - 1)
    } finally {
      isUndoRedoRef.current = false
    }
  }, [update])

  const handleRedo = useCallback(async () => {
    const idx = historyIdxRef.current
    if (idx >= historyRef.current.length - 1) return
    const next = historyRef.current[idx + 1]
    isUndoRedoRef.current = true
    try {
      await update(next)
      historyIdxRef.current = idx + 1
      setHistoryPos(idx + 1)
    } finally {
      isUndoRedoRef.current = false
    }
  }, [update])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); handleUndo() }
      if ((e.ctrlKey || e.metaKey) && e.key === 'z' && e.shiftKey) { e.preventDefault(); handleRedo() }
      if ((e.ctrlKey || e.metaKey) && e.key === 'y') { e.preventDefault(); handleRedo() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [handleUndo, handleRedo])

  // Restore UI state from project on load / project change
  useEffect(() => {
    if (!project) return
    // Restore timeline settings
    if (typeof project.perImageDuration === 'number') setPerImageDuration(project.perImageDuration)
    if (typeof project.shuffleMode === 'boolean') setShuffleMode(project.shuffleMode)
    if (typeof project.cueMode === 'string') setCueMode(project.cueMode)
    // Restore BGM tracks
    if (project.audio?.bgm?.tracks?.length) {
      setBgmTracks(project.audio.bgm.tracks)
    } else if (project.audio?.bgm?.file) {
      // 兼容旧数据：单文件 BGM → 转为 tracks 格式
      setBgmTracks([{
        file: project.audio.bgm.file,
        volume: project.audio.bgm.volume ?? 0.3,
        trimStart: 0, trimEnd: 0, fadeIn: 0, fadeOut: 0,
      }])
    }
    // Restore voiceover-derived state so UI shows "generated" after refresh
    const activeVo = selectActiveVoiceover(project.audio)
    if (activeVo?.file) {
      setGenerated(true)
      setActiveVoiceoverId(activeVo.id || null)
      if (Array.isArray(project.subtitles) && project.subtitles.length > 0) {
        setSubtitleCount(project.subtitles.length)
        const last = project.subtitles[project.subtitles.length - 1]
        setDuration(last.end || activeVo.duration || 0)
      } else if (activeVo.duration) {
        setDuration(activeVo.duration)
      }
    } else {
      setGenerated(false)
      setActiveVoiceoverId(null)
      setDuration(0)
      setSubtitleCount(0)
    }
  }, [project?.id]) // only on project change, not every render

  // Load jianying status + TTS settings
  useEffect(() => {
    api.getJianyingStatus().then(setJianyingStatus).catch(() => setJianyingStatus({ detected: false, path: null, drafts: [] }))
    api.getTtsSettings().then(setTtsSettings).catch(() => null)
  }, [])

  // --- Shared timeline builder: fills target duration from an asset pool ---
  const buildTimeline = useCallback((
    assets: any[],
    targetDuration: number,
    options: { shuffle?: boolean; perImageDuration?: number; blocks?: any[]; selectedAssetPath?: string } = {}
  ) => {
    if (targetDuration <= 0) return []
    const blocks = options.blocks?.length ? options.blocks : (project?.timeline?.blocks?.length ? project.timeline.blocks : [
      { type: 'assets', duration: 'rest', source: 'all', mode: options.shuffle ?? shuffleMode ? 'random' : 'ordered', perAssetDuration: options.perImageDuration ?? perImageDuration }
    ])

    const pickPool = (source: string) => assets.filter((a: any) =>
      source === 'all' || (source === 'images' && a.type === 'image') || (source === 'videos' && a.type === 'video')
    )

    const segs: any[] = []
    let cursor = 0
    blocks.forEach((block: any, blockIndex: number) => {
      if (cursor >= targetDuration - 1e-6) return
      const rawDur = block.duration ?? 'rest'
      const blockDur = Math.max(0, Math.min(rawDur === 'rest' ? targetDuration - cursor : Number(rawDur || 0), targetDuration - cursor))
      if (blockDur <= 0) return

      if (block.type === 'black') {
        segs.push({
          id: `seg_black_${blockIndex}`,
          assetPath: '',
          type: 'black',
          start: cursor,
          end: cursor + blockDur,
          transform: { x: 0.5, y: 0.5, scale: 1, rotation: 0, fit: 'stretch' },
          bgColor: block.bgColor || '#000000'
        })
        cursor += blockDur
        return
      }

      const pool = pickPool(block.source || 'all')
      if (!pool.length) { cursor += blockDur; return }

      if (visualMode === 'single') {
        const selectedPath = options.selectedAssetPath || primaryVisualSegment?.assetPath || ''
        const selected = selectedPath
          ? pool.find((asset: any) => asset.path === selectedPath)
          : pool.length === 1 ? pool[0] : null
        if (!selected) { cursor += blockDur; return }

        const previous = primaryVisualSegment?.assetPath === selected.path ? primaryVisualSegment : null
        const type = selected.type === 'video' ? 'video' : 'image'
        segs.push({
          id: `seg_single_${blockIndex}`,
          assetPath: selected.path,
          type,
          start: cursor,
          end: cursor + blockDur,
          transform: previous?.transform || { x: 0.5, y: 0.5, scale: 0.85, rotation: 0, fit: 'contain' },
          ...(previous?.animation ? { animation: previous.animation } : {}),
        })
        cursor += blockDur
        return
      }

      const ordered = (block.mode || (options.shuffle ?? shuffleMode ? 'random' : 'ordered')) === 'random'
        ? [...pool].sort(() => Math.random() - 0.5)
        : [...pool]
      const per = Math.max(0.05, Number(block.perAssetDuration || options.perImageDuration || perImageDuration || 1))
      const blockEnd = cursor + blockDur
      let idx = 0
      const maxItems = Math.max(1, Math.min(10000, Math.ceil(blockDur / 0.05) + ordered.length + 2))
      while (cursor < blockEnd - 1e-6 && idx < maxItems) {
        const asset = ordered[idx % ordered.length]
        const mtype = asset.type === 'video' ? 'video' : 'image'
        const segDur = Math.min(per, blockEnd - cursor)
        const start = cursor
        cursor += segDur
        segs.push({
          id: `seg_${blockIndex}_${idx}`,
          assetPath: asset.path,
          type: mtype,
          start,
          end: Math.min(cursor, targetDuration),
          transform: { x: 0.5, y: 0.5, scale: 0.85, rotation: 0, fit: 'contain' }
        })
        idx++
      }
    })
    return segs
  }, [project?.timeline?.blocks, shuffleMode, perImageDuration, visualMode, primaryVisualSegment])

  // Voiceover audio URL with cache-busting so regeneration refreshes the player
  const activeVoiceover = useMemo(() => selectActiveVoiceover(project?.audio), [project?.audio])
  const audioBaseUrl = activeVoiceover?.file && id ? api.getVoiceoverUrl(id, activeVoiceover.file) : ''
  const audioUrl = audioBaseUrl ? `${audioBaseUrl}?v=${voiceoverVersion}` : ''

  const handleGenerate = useCallback(async (text: string, engine?: string) => {
    setGenerating(true)
    voiceoverProgress.start('生成配音中...')
    try {
      const selectedEngine = engine || ttsSettings?.engine || 'edge'
      const speed = selectedEngine === 'edge'
        ? Number(ttsSettings?.edgeRate ?? 0)
        : selectedEngine === 'fish_audio'
          ? Number(ttsSettings?.fishSpeed ?? 1.0)
          : selectedEngine === 'volcengine'
            ? Number(ttsSettings?.volcSpeechRate ?? 0)
          : Number(ttsSettings?.customSpeed ?? 0)
      const pitch = selectedEngine === 'edge' ? Number(ttsSettings?.edgePitch ?? 0) : 0
      const result = await api.generateVoiceover(id!, text, speed, pitch, selectedEngine)
      const totalDur = result.duration
      setDuration(totalDur)
      setSubtitleCount(result.subtitleCount)
      setGenerated(true)
      setVoiceoverVersion(v => v + 1)
      setActiveVoiceoverId(result.voiceoverId || null)

      // Merge subtitles with current font size
      const currentFontSize = project?.subtitles?.[0]?.style?.fontSize || 48
      const merged = (result.subtitles || []).map((sub: any) => ({
        ...sub,
        style: { ...sub.style, fontSize: currentFontSize }
      }))

      // Batch images/videos: voiceover drives duration, assets cycle to fill
      let segments: any[]
      const allAssets = projectAssets.length > 0 ? projectAssets :
        (project?.assets || []).filter((a: any) => a.type === 'image' || a.type === 'video')

      const targetDur = (project?.timeline?.voiceoverStartAt || 0) + (totalDur > 0 ? totalDur : 5.0) + 0.5 // black/quiet lead-in + voiceover

      if (allAssets.length >= 1) {
        // Use unified buildTimeline — no more inline segment creation
        segments = buildTimeline(allAssets, targetDur)
      } else if (project?.segments?.[0]?.assetPath) {
        // Single image: keep existing segment, span full duration
        segments = [{
          ...project.segments[0],
          start: 0,
          end: targetDur,
        }]
      } else {
        segments = []
      }

      await update({ subtitles: merged, segments })
      voiceoverProgress.finish('配音已生成')
    } catch (e: any) {
      voiceoverProgress.fail()
      showToast('error', '配音生成失败: ' + e.message)
    } finally {
      setGenerating(false)
    }
  }, [id, update, showToast, project, projectAssets, shuffleMode, perImageDuration, buildTimeline, ttsSettings])

  const handleTtsSettingsChange = useCallback(async (s: any) => {
    setTtsSettings(s)
    try { await api.updateTtsSettings(s) } catch { /* ignore */ }
  }, [])

  const handleSubtitleFontSizeChange = useCallback(async (size: number) => {
    const currentSubs = project?.subtitles || []
    const updated = currentSubs.map((sub: any) => ({
      ...sub,
      style: { ...(sub.style || {}), fontSize: size }
    }))
    await update({ subtitles: updated })
  }, [project, update])

  const handleSubtitleEnabledChange = useCallback(async (v: boolean) => {
    const currentOverlays = project?.overlays || {}
    await update({ overlays: { ...currentOverlays, subtitle_enabled: v } })
  }, [project, update])

  const handleSubtitlePositionChange = useCallback(async (pos: string) => {
    const currentSubs = project?.subtitles || []
    if (currentSubs.length === 0) return
    /*
    if (currentSubs.length === 0) return  // 无字幕时只更新本地状态
    const updated = currentSubs.map((sub: any) => ({
    */
    const updated = currentSubs.map((sub: any) => ({
      ...sub,
      style: { ...(sub.style || {}), position: pos }
    }))
    await update({ subtitles: updated })
  }, [project, update])

  const validateExportReady = useCallback(() => {
    if (!generated || !activeVoiceover?.file) return '请先在「文案」Tab 生成配音。'
    if (!primaryVisualSegment?.assetPath) {
      return visualMode === 'single'
        ? '请先在「素材」Tab 选择一张贯穿全片的图片。'
        : '请先在「素材」Tab 添加素材并生成轮播。'
    }
    return ''
  }, [generated, activeVoiceover?.file, primaryVisualSegment?.assetPath, visualMode])
  const isExportReady = generated && !!activeVoiceover?.file && !!primaryVisualSegment?.assetPath

  const handleExportZip = useCallback(async () => {
    const missing = validateExportReady()
    if (missing) { showToast('error', missing); return }
    setExporting(true)
    exportProgress.start('导出草稿中...')
    try {
      await api.exportJianying(id!, cueMode)
      exportProgress.finish('导出完成')
      showToast('ok', '草稿 ZIP 已下载')
    } catch (e: any) {
      exportProgress.fail()
      showToast('error', '导出失败: ' + e.message)
    } finally {
      setExporting(false)
    }
  }, [id, cueMode, showToast, validateExportReady])

  const handleSaveTemplate = useCallback(async () => {
    const name = prompt('模板名称：', project?.name + ' 模板')
    if (!name) return
    try {
      await api.saveTemplate({
        name,
        templateId: project?.templateId,
        visualMode,
        canvas: project?.canvas,
        overlays: project?.overlays,
        audio: project?.audio,
        timeline: project?.timeline,
        perImageDuration: project?.perImageDuration,
        shuffleMode: project?.shuffleMode,
      })
      showToast('ok', '模板已保存')
    } catch (e: any) {
      showToast('error', '保存模板失败: ' + e.message)
    }
  }, [project, showToast, visualMode])

  const handleExportDirect = useCallback(async () => {
    const missing = validateExportReady()
    if (missing) { showToast('error', missing); return }
    setExporting(true)
    exportProgress.start('导出到剪映...')
    try {
      const job = await api.startExportJianyingDirectJob(id!, cueMode)
      const result = await waitForJob<{ status: string; message: string; path: string; draft_name: string }>(
        job.jobId,
        exportProgress,
        '导出到剪映...'
      )
      exportProgress.finish('已写入剪映')
      showToast('ok', `已导出到剪映：「${result.draft_name}」`)
    } catch (e: any) {
      exportProgress.fail()
      showToast('error', '导出到剪映失败: ' + e.message)
    } finally {
      setExporting(false)
    }
  }, [id, cueMode, showToast, validateExportReady, waitForJob, exportProgress])

  const handleSyncJianyingParams = useCallback(async () => {
    setSyncingJianying(true)
    exportProgress.start('读取剪映参数...')
    try {
      const result = await api.syncJianyingParams(id!)
      await reload()
      exportProgress.finish('剪映参数已同步')
      showToast('ok', `已同步：素材 ${result.changes.segments} 个，字幕 ${result.changes.subtitles} 条`)
    } catch (e: any) {
      exportProgress.fail()
      showToast('error', '同步剪映参数失败: ' + e.message)
    } finally {
      setSyncingJianying(false)
    }
  }, [id, reload, showToast, exportProgress])

  const handleGeneratePreview = useCallback(async () => {
    const missing = validateExportReady()
    if (missing) { showToast('error', missing); return }
    setRendering(true)
    renderProgress.start('渲染预览中...')
    previewProjectVersionRef.current = ''
    setPreviewUrl('')
    try {
      const job = await api.startPreviewJob(id!, cueMode)
      const result = await waitForJob<{ status: string; previewUrl: string; duration: number }>(
        job.jobId,
        renderProgress,
        '渲染预览...'
      )
      renderProgress.finish('渲染完成')
      previewProjectVersionRef.current = project?.updated_at || ''
      setPreviewUrl(result.previewUrl)
      showToast('ok', `预览已生成 (${result.duration.toFixed(1)}s)`)
    } catch (e: any) {
      renderProgress.fail()
      showToast('error', '预览渲染失败: ' + e.message)
    } finally {
      setRendering(false)
    }
  }, [id, cueMode, showToast, validateExportReady, waitForJob, renderProgress, project?.updated_at])

  const handleAssetChange = useCallback(async (path: string, assetMeta?: any) => {
    const currentAssets = project?.assets || []
    if (!path) {
      const blackSegments = (project?.segments || []).filter((segment: any) => segment.type === 'black')
      await update({ segments: blackSegments })
      return
    }

    const filename = String(assetMeta?.name || assetMeta?.filename || path.split(/[\\/]/).pop() || 'asset')
    const extension = filename.split('.').pop()?.toLowerCase() || ''
    const type = assetMeta?.type === 'video' || ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(extension)
      ? 'video'
      : 'image'
    const exists = currentAssets.some((asset: any) => asset.path === path)
    const updatedAssets = exists ? currentAssets : [
      ...currentAssets,
      { id: assetMeta?.id || `asset_${Date.now()}`, type, name: filename, path },
    ]
    const target = (project?.timeline?.voiceoverStartAt || 0) + (duration > 0 ? duration : 5) + 0.5
    const segments = visualMode === 'single'
      ? buildTimeline(updatedAssets, target, { selectedAssetPath: path })
      : generated && duration > 0
        ? buildTimeline(updatedAssets, target)
        : (project?.segments || [])

    await update({ segments, assets: updatedAssets })
  }, [duration, update, project, visualMode, generated, buildTimeline])

  const handleBatchAssetsChange = useCallback(async (newAssets: any[]) => {
    const target = (project?.timeline?.voiceoverStartAt || 0) + (duration > 0 ? duration : 5) + 0.5
    const selectedPath = primaryVisualSegment?.assetPath || ''
    const retainedPath = newAssets.some((asset: any) => asset.path === selectedPath)
      ? selectedPath
      : newAssets.length === 1 ? newAssets[0].path : ''
    const blackSegments = (project?.segments || []).filter((segment: any) => segment.type === 'black')
    const segments = visualMode === 'single'
      ? retainedPath ? buildTimeline(newAssets, target, { selectedAssetPath: retainedPath }) : blackSegments
      : generated && duration > 0 ? buildTimeline(newAssets, target) : []

    await update({ assets: newAssets, segments })
  }, [update, project, duration, primaryVisualSegment, visualMode, generated, buildTimeline])

  const handleInsertOpeningBlack = useCallback(async () => {
    try {
      const opener = { type: 'black', duration: 3, bgColor: '#000000' }
      const currentBlocks = project?.timeline?.blocks || []
      const restBlocks = currentBlocks.length && currentBlocks[0]?.type === 'black'
        ? currentBlocks.slice(1)
        : currentBlocks
      const assetBlock = {
        type: 'assets',
        duration: 'rest',
        source: 'all',
        mode: shuffleMode ? 'random' : 'ordered',
        perAssetDuration: perImageDuration,
      }
      const contentBlocks = restBlocks.length ? restBlocks : [assetBlock]
      const normalizedContentBlocks = contentBlocks.length === 1 && contentBlocks[0]?.type === 'assets'
        ? [{ ...assetBlock, ...contentBlocks[0], duration: 'rest' }]
        : contentBlocks
      const blocks = [opener, ...normalizedContentBlocks]
      const timeline = {
        ...(project?.timeline || {}),
        voiceoverStartAt: 3,
        blocks,
      }
      const allAssets = projectAssets.length > 0 ? projectAssets :
        (project?.assets || []).filter((a: any) => a.type === 'image' || a.type === 'video')
      const target = 3 + (duration > 0 ? duration : 5) + 0.5
      const segments = buildTimeline(allAssets, target, { blocks })
      await update({ timeline, segments })
      showToast('ok', '已插入 3 秒片头黑幕；配音从 3 秒开始，BGM 保持原起点。')
      return true
    } catch (e: any) {
      showToast('error', '插入片头黑幕失败: ' + e.message)
      throw e
    }
  }, [project, projectAssets, duration, shuffleMode, perImageDuration, buildTimeline, update, showToast])

  const handleTimelineChange = useCallback(async (timeline: any) => {
    const allAssets = projectAssets.length > 0 ? projectAssets :
      (project?.assets || []).filter((a: any) => a.type === 'image' || a.type === 'video')
    const target = (timeline?.voiceoverStartAt || 0) + (duration > 0 ? duration : 5) + 0.5
    const segments = buildTimeline(allAssets, target, { blocks: timeline?.blocks || [] })
    await update({ timeline, segments })
  }, [projectAssets, project, duration, buildTimeline, update])

  // Generate carousel: fill target duration, cycle assets if needed, trim if excess
  const handleGenerateCarousel = useCallback(async () => {
    try {
      if (visualMode !== 'carousel') return false
      // MUST have voiceover first — video duration is driven by voiceover
      if (!generated || duration <= 0) {
        showToast('error', '请先在「文案」Tab 生成配音，视频时长以配音为准。')
        return false
      }

      const allAssets = projectAssets.length > 0 ? projectAssets :
        (project?.assets || []).filter((a: any) => a.type === 'image' || a.type === 'video')
      if (allAssets.length < 1) {
        showToast('error', '请先上传或导入素材。')
        return false
      }

      const target = (project?.timeline?.voiceoverStartAt || 0) + duration + 0.5
      const segs = buildTimeline(allAssets, target)
      await update({ segments: segs })
      showToast('ok', `轮播已生成：${segs.length} 段素材填满 ${duration.toFixed(1)}s 配音`)
      return true
    } catch (e: any) {
      showToast('error', '生成轮播失败: ' + e.message)
      throw e
    }
  }, [projectAssets, project, duration, generated, update, showToast, buildTimeline, visualMode])

  const handlePerImageDurationChange = useCallback(async (v: number) => {
    setPerImageDuration(v)
    await update({ perImageDuration: v })
  }, [update])

  const handleCueModeChange = useCallback(async (v: string) => {
    setCueMode(v)
    await update({ cueMode: v })
  }, [update])

  const handleShuffleModeChange = useCallback(async (v: boolean) => {
    setShuffleMode(v)
    await update({ shuffleMode: v })
    if (visualMode === 'carousel' && projectAssets.length > 1 && generated && duration > 0) {
      const target = (project?.timeline?.voiceoverStartAt || 0) + duration + 0.5
      const segs = buildTimeline(projectAssets, target, { shuffle: v })
      await update({ segments: segs })
    }
  }, [projectAssets, project, generated, duration, update, buildTimeline, visualMode])

  const handleScaleChange = useCallback(async (newScale: number) => {
    const currentSegments = project?.segments || []
    if (currentSegments.length === 0) return
    const updated = currentSegments.map((seg: any) => ({
      ...seg,
      ...(seg.type === 'black' ? {} : { transform: { ...seg.transform, scale: newScale } })
    }))
    await update({ segments: updated })
  }, [project, update])

  const handlePositionChange = useCallback(async (x: number, y: number) => {
    const currentSegments = project?.segments || []
    if (currentSegments.length === 0) return
    const updated = currentSegments.map((seg: any) => ({
      ...seg,
      ...(seg.type === 'black' ? {} : { transform: { ...seg.transform, x, y } })
    }))
    await update({ segments: updated })
  }, [project, update])

  const handleFitChange = useCallback(async (newFit: string) => {
    const currentSegments = project?.segments || []
    if (currentSegments.length === 0) return
    const updated = currentSegments.map((seg: any) => ({
      ...seg,
      ...(seg.type === 'black' ? {} : { transform: { ...seg.transform, fit: newFit } })
    }))
    await update({ segments: updated })
  }, [project, update])

  const handleTitlePositionChange = useCallback(async (x: number, y: number) => {
    const t = project?.overlays?.title || {}
    await update({ overlays: { ...project?.overlays, title: { ...t, x, y } } })
  }, [project, update])

  const handleWatermarkPositionChange = useCallback(async (x: number, y: number) => {
    const w = project?.overlays?.watermark || {}
    await update({ overlays: { ...project?.overlays, watermark: { ...w, x, y } } })
  }, [project, update])

  const handleSwitchVoiceover = useCallback(async (voiceoverId: string) => {
    voiceoverProgress.start('切换配音中...')
    try {
      const result = await api.switchVoiceover(id!, voiceoverId)
      setActiveVoiceoverId(voiceoverId)
      setDuration(result.duration)
      setSubtitleCount(result.subtitleCount)
      setVoiceoverVersion(v => v + 1)
      await update({
        subtitles: result.subtitles,
        audio: { ...project?.audio, voiceovers: result.voiceovers, voiceover: result.voiceovers.find((v: any) => v.isActive) },
      })
      voiceoverProgress.finish('已切换配音')
      showToast('ok', `已切换配音，时长 ${result.duration.toFixed(1)}s`)
    } catch (e: any) {
      voiceoverProgress.fail()
      showToast('error', '切换配音失败: ' + e.message)
    }
  }, [id, project, update, showToast, voiceoverProgress])

  const handleDeleteVoiceover = useCallback(async (voiceoverId: string) => {
    try {
      const result = await api.deleteVoiceover(id!, voiceoverId)
      const active = result.voiceovers.find((v: any) => v.id === result.activeId)
      setActiveVoiceoverId(result.activeId)
      setDuration(active?.duration || 0)
      setVoiceoverVersion(v => v + 1)
      await update({
        audio: { ...project?.audio, voiceovers: result.voiceovers, voiceover: active },
      })
      showToast('ok', '已删除配音')
    } catch (e: any) {
      showToast('error', '删除配音失败: ' + e.message)
    }
  }, [id, project, update, showToast])

  const handleRatioChange = useCallback(async (ratio: string) => {
    const r = RATIOS.find(r => r.key === ratio)
    if (!r || !project) return
    await update({ canvas: { ...project.canvas, ratio: r.key, width: r.w, height: r.h } })
  }, [project, update])

  const handleBgColorChange = useCallback(async (color: string) => {
    if (project) {
      await update({ canvas: { ...project.canvas, background: { type: 'color', value: color } } })
    }
  }, [project, update])

  if (loading) {
    return (
      <div className="min-h-[100dvh] flex items-center justify-center workbench-shell brand-rift">
        <div className="status-pill px-3 py-2 text-xs animate-surface-in" data-tone="warn">加载中…</div>
      </div>
    )
  }
  if (!project) {
    const title = error?.startsWith('500:') ? '项目加载失败' : '未找到项目'
    return (
      <div className="min-h-[100dvh] flex flex-col items-center justify-center workbench-shell brand-rift gap-4 px-4">
        <div className="brand-frame px-6 py-6 max-w-md w-full text-center space-y-3 animate-surface-in">
          <div className="text-base font-heading font-semibold tracking-[0.08em]" style={{ color: 'var(--text-primary)' }}>{title}</div>
          <div className="text-xs italic" style={{ color: 'var(--text-secondary)' }}>
            项目 ID: <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{id}</span>
            {error && <div className="mt-2" style={{ color: 'var(--danger)' }}>错误: {error}</div>}
          </div>
          <div className="flex gap-2 justify-center pt-1">
            <button onClick={() => window.location.reload()} className="btn-cinematic px-4 py-2 text-xs">
              重新加载
            </button>
            <button onClick={() => navigate('/')} className="btn-gold px-4 py-2 text-xs">
              返回首页
            </button>
          </div>
        </div>
      </div>
    )
  }
  if (!project) {
    return (
      <div className="min-h-[100dvh] flex flex-col items-center justify-center workbench-shell brand-rift gap-4 px-4">
        <div className="brand-frame px-6 py-6 max-w-md w-full text-center space-y-3 animate-surface-in">
          <div className="text-base font-heading font-semibold tracking-[0.08em]" style={{ color: 'var(--text-primary)' }}>未找到项目</div>
          <div className="text-xs italic" style={{ color: 'var(--text-secondary)' }}>
            项目 ID: <span className="font-mono" style={{ color: 'var(--text-primary)' }}>{id}</span>
            {error && <div className="mt-2" style={{ color: 'var(--danger)' }}>错误: {error}</div>}
          </div>
          <div className="flex gap-2 justify-center pt-1">
            <button onClick={() => window.location.reload()} className="btn-cinematic px-4 py-2 text-xs">重新加载</button>
            <button onClick={() => navigate('/')} className="btn-gold px-4 py-2 text-xs">返回首页</button>
          </div>
        </div>
      </div>
    )
  }

  const currentRatio = project.canvas?.ratio || '9:16'
  const currentScale = primaryVisualSegment?.transform?.scale || 0.85
  const currentFit = primaryVisualSegment?.transform?.fit || 'contain'
  const currentPositionX = primaryVisualSegment?.transform?.x ?? 0.5
  const currentPositionY = primaryVisualSegment?.transform?.y ?? 0.5
  const subtitleEnabled = project.overlays?.subtitle_enabled ?? true
  const leadInDuration = Number(project.timeline?.voiceoverStartAt || 0)
  const segmentCount = project.segments?.length || 0
  const projectAssetCount = projectAssets.length
  const totalTimelineDuration = leadInDuration + (duration > 0 ? duration : 0) + 0.5
  const readinessMissing = !generated || !activeVoiceover?.file
    ? '配音'
    : segmentCount === 0
      ? '素材'
      : ''
  const readinessLabel = readinessMissing ? `缺 ${readinessMissing}` : '导出就绪'
  const readinessTone: 'ok' | 'warn' | 'danger' = readinessMissing ? 'warn' : 'ok'

  const TABS = [
    { key: 'script' as const, icon: TextAa, label: '文案' },
    { key: 'assets' as const, icon: Images, label: '素材' },
    { key: 'adjust' as const, icon: Sliders, label: '调整' },
    { key: 'export' as const, icon: Export, label: '导出' },
    ...(project.structuredContent ? [{ key: 'structured' as const, icon: Sliders, label: '链式内容' }] : []),
  ]

  return (
    <div className="h-[100dvh] flex flex-col overflow-hidden workbench-shell">
      <TopBar
        projectName={project.name}
        onExportZip={handleExportZip}
        onExportDirect={handleExportDirect}
        onSaveTemplate={handleSaveTemplate}
        exporting={exporting}
        exportReady={isExportReady}
        jianyingStatus={jianyingStatus}
        saveStatus={saveStatus}
        readinessLabel={readinessLabel}
        readinessTone={readinessTone}
      />
      {(voiceoverProgress.active || renderProgress.active || exportProgress.active) && (
        <div className="shrink-0 px-3 py-2 border-b space-y-1" style={{ background: 'var(--bg-surface)', borderColor: 'var(--border-subtle)' }}>
          <LoadingProgress active={voiceoverProgress.active} progress={voiceoverProgress.progress} label={voiceoverProgress.label} failed={voiceoverProgress.failed} />
          <LoadingProgress active={renderProgress.active} progress={renderProgress.progress} label={renderProgress.label} failed={renderProgress.failed} />
          <LoadingProgress active={exportProgress.active} progress={exportProgress.progress} label={exportProgress.label} failed={exportProgress.failed} />
        </div>
      )}

      <div className="px-3 pt-2">
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.22, ease: 'easeOut' }}
          className="timeline-strip px-3 py-2 flex flex-wrap items-center gap-2 text-[10px]"
        >
          <span className="status-pill px-2 py-1" data-tone={leadInDuration > 0 ? 'warn' : 'ok'}>片头 {leadInDuration.toFixed(1)}s</span>
          <span className="status-pill px-2 py-1" data-tone="ok">{visualMode === 'single' ? '单图贯穿' : '多图轮播'}</span>
          <span className="status-pill px-2 py-1" data-tone={generated ? 'ok' : 'warn'}>配音 {duration.toFixed(1)}s</span>
          <span className="status-pill px-2 py-1" data-tone={projectAssetCount > 0 ? 'ok' : 'warn'}>素材 {projectAssetCount} 个</span>
          <span className="status-pill px-2 py-1" data-tone={segmentCount > 0 ? 'ok' : 'warn'}>片段 {segmentCount} 段</span>
          <span className="status-pill px-2 py-1" data-tone={bgmTracks.length > 0 ? 'ok' : 'warn'}>BGM {bgmTracks.length} 首</span>
          <span className="status-pill px-2 py-1" data-tone={totalTimelineDuration > 0 ? 'ok' : 'warn'}>总长 {totalTimelineDuration.toFixed(1)}s</span>
        </motion.div>
      </div>

      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden min-h-0">
        {/* Left: toolbar + preview */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="h-auto lg:h-12 border-b px-3 lg:px-4 py-3 lg:py-0 flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-3 shrink-0 toolbar-glass">
            <RatioGroup ratios={RATIOS} value={currentRatio} onChange={handleRatioChange} />
            <div className="flex flex-wrap items-center gap-2">
              <button onClick={handleUndo} disabled={historyPos <= 0}
                className="icon-button" title="撤销 Ctrl+Z">
                <ArrowUUpLeft size={16} weight="bold" />
              </button>
              <button onClick={handleRedo} disabled={historyPos >= historyLen - 1}
                className="icon-button" title="重做 Ctrl+Shift+Z">
                <ArrowUUpRight size={16} weight="bold" />
              </button>
              <div className="w-px h-5 mx-1" style={{ background: 'var(--border-subtle)' }} />
              <ScaleControl scale={currentScale} onChange={handleScaleChange} disabled={!primaryVisualSegment?.assetPath} />
              <FitControl fit={currentFit} onChange={handleFitChange} disabled={!primaryVisualSegment?.assetPath} />
              <div className="w-px h-5 mx-1" style={{ background: 'var(--border-subtle)' }} />
              <button onClick={handleGeneratePreview} disabled={rendering || !isExportReady}
                className="btn-gold flex items-center gap-1.5 text-xs disabled:opacity-40">
                {rendering ? <Spinner size={14} className="animate-spin" weight="bold" /> : <Play size={14} weight="fill" />}
                {rendering ? '渲染中...' : previewUrl ? '重新渲染' : '预览'}
              </button>
            </div>
          </div>
          <div className="px-2">
            <LoadingProgress active={renderProgress.active} progress={renderProgress.progress} label={renderProgress.label} failed={renderProgress.failed} />
          </div>
          <div className="flex-1 relative min-h-0">
            {previewUrl ? (
              <div className="absolute inset-0 flex items-center justify-center p-4">
                <button
                  onClick={() => setPreviewUrl('')}
                  className="icon-button absolute top-5 right-5 z-10"
                  style={{ background: 'var(--bg-surface)', boxShadow: 'var(--shadow-sm)' }}
                  aria-label="关闭渲染预览"
                  title="关闭渲染预览，返回编辑预览"
                >
                  <X size={16} weight="bold" />
                </button>
                <video src={previewUrl} controls autoPlay
                  onPlay={() => { document.querySelectorAll('audio').forEach(a => a.pause()) }}
                  className="max-w-full max-h-full rounded-lg shadow-lg border"
                  style={{
                    borderColor: 'var(--border)',
                    background: 'var(--bg-base)',
                    aspectRatio: `${project.canvas?.width || 1080} / ${project.canvas?.height || 1920}`,
                  }} />
              </div>
            ) : (
              <CanvasPreview
                projectId={id!} imagePath={primaryVisualSegment?.assetPath || null}
                scale={currentScale} fit={currentFit}
                positionX={currentPositionX} positionY={currentPositionY}
                canvasW={project.canvas?.width || 1080} canvasH={project.canvas?.height || 1920}
                bgColor={bgColor} subtitles={project.subtitles || []}
                subtitleFontSize={subtitleFontSize} subtitleEnabled={subtitleEnabled}
                subtitlePosition={subtitlePosition}
                segmentType={primaryVisualSegment?.type || 'image'}
                materialCount={visualMode === 'carousel' ? (project.segments || []).filter((segment: any) => segment.type !== 'black').length : 0}
                shuffleMode={shuffleMode}
                onPositionChange={handlePositionChange}
                totalDuration={duration + (project.timeline?.voiceoverStartAt || 0) + 0.5}
                voiceoverStartAt={project.timeline?.voiceoverStartAt || 0}
                voiceoverDuration={duration}
                voiceoverUrl={generated && audioUrl ? audioUrl : null}
                title={project.overlays?.title || {}}
                watermark={project.overlays?.watermark || {}}
                directoryProgress={project.overlays?.directoryProgress || {}}
                brightness={adjustments.brightness}
                contrast={adjustments.contrast}
                onTitlePositionChange={handleTitlePositionChange}
                onWatermarkPositionChange={handleWatermarkPositionChange} />
            )}
          </div>
        </div>

        {/* Right: Tab sidebar */}
        <div className="w-full lg:w-[clamp(320px,28vw,400px)] shrink-0 lg:border-l border-t lg:border-t-0 flex flex-col min-h-0 toolbar-glass">
          {/* Tab bar */}
          <div className="flex border-b shrink-0" style={{ borderColor: 'var(--border-subtle)' }}>
            {TABS.map(tab => {
              const Icon = tab.icon
              return (
                <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2.5 text-[11px] font-heading font-semibold tracking-[0.12em] transition-all border-b-2 ${
                    activeTab === tab.key
                      ? 'selected-surface'
                      : 'border-transparent hover:bg-[var(--bg-surface)]'
                  }`}
                  style={activeTab === tab.key ? undefined : { color: 'var(--text-secondary)' }}>
                  <Icon size={14} weight={activeTab === tab.key ? 'fill' : 'regular'} />
                  {tab.label}
                </button>
              )
            })}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto min-h-0">
            <div className="p-4 space-y-4">
              {activeTab === 'assets' && (
                <AssetPanel
                  projectId={id!} assetPath={primaryVisualSegment?.assetPath || null}
                  visualMode={visualMode}
                  imageAssets={projectAssets} shuffleMode={shuffleMode}
                  perImageDuration={perImageDuration}
                  voiceoverGenerated={generated}
                  onAssetChange={handleAssetChange}
                  onBatchAssetsChange={handleBatchAssetsChange}
                  onShuffleModeChange={handleShuffleModeChange}
                  onPerImageDurationChange={handlePerImageDurationChange}
                  onGenerateCarousel={visualMode === 'carousel' ? handleGenerateCarousel : undefined}
                  onInsertOpeningBlack={handleInsertOpeningBlack} />
              )}
              {activeTab === 'script' && (
                <div className="space-y-4">
                  <ScriptPanel
                    onGenerate={handleGenerate} generating={generating}
                    generated={generated} subtitleCount={subtitleCount}
                    duration={duration} audioUrl={audioUrl} projectId={id!}
                    ttsSettings={ttsSettings} onTtsSettingsChange={handleTtsSettingsChange}
                    progress={voiceoverProgress}
                    subtitles={project?.subtitles}
                    script={project?.script || ''}
                    onScriptChange={async (text) => await update({ script: text })}
                    onSrtImported={async (result) => {
                      await reload()
                      const ignored = Number(result.ignoredCount || 0)
                      showToast('ok', ignored > 0
                        ? `已导入 ${result.subtitleCount} 条字幕，忽略 ${ignored} 个无效片段`
                        : `已导入 ${result.subtitleCount} 条字幕`)
                    }}
                    onSrtError={(message) => showToast('error', message)}
                    voiceovers={project?.audio?.voiceovers || []}
                    activeVoiceoverId={activeVoiceoverId}
                    onSwitchVoiceover={handleSwitchVoiceover}
                    onDeleteVoiceover={handleDeleteVoiceover}
                    onSubtitleUpdate={async (idx, newText) => {
                      const subs = [...(project?.subtitles || [])]
                      subs[idx] = { ...subs[idx], text: newText }
                      await update({ subtitles: subs })
                    }} />
                  <AudioPanel
                    projectId={id!} bgmTracks={bgmTracks}
                    sfxTracks={project.audio?.sfx || []}
                    voiceoverVolume={activeVoiceover?.volume ?? 1.0}
                    voiceoverUrl={audioUrl}
                    onBgmTracksChange={async (tracks) => {
                      setBgmTracks(tracks)
                      await update({ audio: { ...project.audio, bgm: { ...project.audio.bgm, tracks } } })
                    }}
                    onSfxTracksChange={async (sfx) => {
                      await update({ audio: { ...project.audio, sfx } })
                    }}
                    onVoiceoverVolumeChange={async (v) => {
                      const active = selectActiveVoiceover(project.audio)
                      if (!active) return
                      const newVoices = (project.audio?.voiceovers || []).map((x: any) => x.id === active?.id ? { ...x, volume: v } : x)
                      await update({ audio: { ...project.audio, voiceovers: newVoices, voiceover: { ...active, volume: v } } })
                    }}
                    onError={(msg) => showToast('error', msg)}
                    cueMode={cueMode} onCueModeChange={handleCueModeChange} />
                </div>
              )}
              {activeTab === 'adjust' && (
                <div className="space-y-4">
                  <OverlayPanel
                    title={project.overlays?.title || {}}
                    watermark={project.overlays?.watermark || {}}
                    subtitleFontSize={subtitleFontSize}
                    subtitleEnabled={subtitleEnabled}
                    subtitlePosition={subtitlePosition}
                    bgColor={bgColor}
                    adjustments={adjustments}
                    directoryProgress={project.overlays?.directoryProgress || {}}
                    onTitleChange={async (t) => await update({ overlays: { ...project.overlays, title: t } })}
                    onWatermarkChange={async (w) => await update({ overlays: { ...project.overlays, watermark: w } })}
                    onSubtitleFontSizeChange={handleSubtitleFontSizeChange}
                    onSubtitleEnabledChange={handleSubtitleEnabledChange}
                    onSubtitlePositionChange={handleSubtitlePositionChange}
                    onBgColorChange={handleBgColorChange}
                    onAdjustmentsChange={async (adj) => {
                      await update({ overlays: { ...project.overlays, adjustments: adj } })
                    }}
                    onDirectoryProgressChange={async (dp) => {
                      await update({ overlays: { ...project.overlays, directoryProgress: dp } })
                    }} />
                  <RhythmPanel
                    timeline={project.timeline || { voiceoverStartAt: 0, blocks: [] }}
                    onTimelineChange={handleTimelineChange}
                  />
                </div>
              )}
              {activeTab === 'export' && (
                <div className="space-y-3">
                  <LoadingProgress active={exportProgress.active} progress={exportProgress.progress} label={exportProgress.label} failed={exportProgress.failed} />
                  <div className="card-cinematic p-4">
                    <h3 className="label-cinematic mb-3">导出到剪映</h3>
                    <button onClick={handleExportDirect} disabled={exporting || !isExportReady}
                      className="btn-gold w-full text-xs py-2.5 disabled:opacity-40">
                      {exporting ? '导出中...' : '一键导出到剪映'}
                    </button>
                    <button onClick={handleSyncJianyingParams} disabled={exporting || syncingJianying || !jianyingStatus?.detected}
                      className="btn-cinematic w-full text-xs py-2.5 mt-2 disabled:opacity-40">
                      {syncingJianying ? '同步中...' : '同步剪映参数'}
                    </button>
                    <p className="text-[10px] mt-2 text-center italic" style={{ color: 'var(--text-muted)' }}>草稿将出现在剪映草稿箱</p>
                  </div>
                  <div className="card-cinematic p-4">
                    <h3 className="label-cinematic mb-3">下载 ZIP</h3>
                    <button onClick={handleExportZip} disabled={exporting || !isExportReady}
                      className="btn-cinematic w-full text-xs py-2.5 disabled:opacity-40">
                      {exporting ? '导出中...' : '下载草稿 ZIP'}
                    </button>
                  </div>
                  <div className="card-cinematic p-4">
                    <h3 className="label-cinematic mb-3">保存为模板</h3>
                    <button onClick={handleSaveTemplate}
                      className="btn-cinematic w-full text-xs py-2.5">
                      保存当前配置为模板
                    </button>
                  </div>
                </div>
              )}
              {activeTab === 'structured' && project.structuredContent && (
                <StructuredPanel projectId={id!} structuredContent={project.structuredContent} onToast={showToast} />
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Bottom audio bar */}
      <div className="min-h-11 border-t flex flex-wrap items-center px-4 py-2 gap-x-4 gap-y-2 shrink-0 toolbar-glass">
        <span className="label-cinematic w-12">配音</span>
        {generated && audioUrl ? (
          <AudioPlayer key={audioUrl} src={audioUrl} />
        ) : (
          <span className="text-[10px] italic flex-1 max-w-xs" style={{ color: 'var(--text-muted)' }}>未生成</span>
        )}
        <div className="w-px h-4" style={{ background: 'var(--border-subtle)' }} />
        <span className="label-cinematic">字幕</span>
        <span className="text-[10px] truncate max-w-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
          {project.subtitles?.length
            ? `${project.subtitles.length} 条 · ${Number(project.subtitles[project.subtitles.length - 1]?.end || duration).toFixed(1)}s`
            : '无字幕'}
        </span>
        <div className="w-px h-4" style={{ background: 'var(--border-subtle)' }} />
        <span className="label-cinematic">BGM</span>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>{bgmTracks.length} 首</span>
        <span className="ml-auto status-pill px-2 py-1 text-[10px]" data-tone={saveStatus === 'error' ? 'danger' : saveStatus === 'saving' ? 'warn' : 'ok'}>
          {saveStatus === 'saving' ? '保存中' : saveStatus === 'error' ? '保存失败' : '已保存'}
        </span>
      </div>

      {toast && (
        <div
          className="fixed bottom-14 left-1/2 -translate-x-1/2 z-50 status-pill px-4 py-2 text-xs font-heading tracking-wide flex items-center gap-2 transition-all animate-fade-in"
          data-tone={toast.type === 'ok' ? 'ok' : 'danger'}
        >
          <span className="font-semibold">{toast.type === 'ok' ? '完成' : '失败'}</span>
          {toast.msg}
        </div>
      )}
    </div>
  )
}

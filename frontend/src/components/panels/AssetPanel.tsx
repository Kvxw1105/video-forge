import { useCallback, useState, useEffect } from 'react'
import { Image, Video, Trash, UploadSimple, FolderOpen, Shuffle, ListNumbers, X, ArrowLeft } from '@phosphor-icons/react'
import { api } from '../../lib/api'
import { useProgress, LoadingProgress } from '../../hooks/useProgress'
import MediaAssetInspector from '../MediaAssetInspector'

const ACCEPT_TYPES = 'image/*,video/*'

export default function AssetPanel({
  projectId, assetPath, visualMode = 'single', imageAssets = [], shuffleMode = true, perImageDuration = 1.0,
  voiceoverGenerated = false,
  onAssetChange, onBatchAssetsChange, onShuffleModeChange, onPerImageDurationChange, onGenerateCarousel, onInsertOpeningBlack,
  onProjectRefresh
}: {
  projectId: string
  assetPath: string | null
  visualMode?: 'single' | 'carousel'
  imageAssets?: any[]
  shuffleMode?: boolean
  perImageDuration?: number
  voiceoverGenerated?: boolean
  onAssetChange: (path: string, meta?: any) => void
  onBatchAssetsChange?: (assets: any[]) => void
  onShuffleModeChange?: (v: boolean) => void
  onPerImageDurationChange?: (v: number) => void
  onGenerateCarousel?: () => Promise<boolean> | boolean
  onInsertOpeningBlack?: () => Promise<boolean> | boolean
  onProjectRefresh?: () => Promise<void>
}) {
  const assetProgress = useProgress()
  const acceptedTypes = visualMode === 'single' ? 'image/*' : ACCEPT_TYPES

  const handleDrop = useCallback(async (e: React.DragEvent) => {
    e.preventDefault()
    const file = e.dataTransfer.files[0]
    const accepted = file && (file.type.startsWith('image/') || (visualMode === 'carousel' && file.type.startsWith('video/')))
    if (file && accepted) {
      assetProgress.start('上传素材...')
      try {
        const r = await api.uploadAsset(projectId, file)
        onAssetChange(r.path, r)
        assetProgress.finish('素材已上传')
      } catch {
        assetProgress.fail('素材上传失败')
      }
    }
  }, [projectId, onAssetChange, assetProgress, visualMode])

  // Library picker state
  const [showLibrary, setShowLibrary] = useState(false)
  const [libraryAssets, setLibraryAssets] = useState<any[]>([])
  const [libraryFolders, setLibraryFolders] = useState<Record<string, any[]>>({})
  const [loadingLibrary, setLoadingLibrary] = useState(false)
  const [selectedFolder, setSelectedFolder] = useState<string | null>(null)
  const [importMode, setImportMode] = useState<'manual' | 'random' | null>(null)

  const openLibrary = useCallback(async () => {
    setShowLibrary(true)
    setSelectedFolder(null)
    setImportMode(null)
    setLoadingLibrary(true)
    assetProgress.start('加载素材库...')
    try {
      const list = await api.listLibrary()
      const media = list.filter((a: any) => a.type === 'image' || a.type === 'video')
      setLibraryAssets(media)
      // Group by folder
      const folders: Record<string, any[]> = {}
      for (const a of media) {
        const f = a.folder || ''
        if (f) {
          const top = f.split('/')[0]
          if (!folders[top]) folders[top] = []
          folders[top].push(a)
        }
      }
      setLibraryFolders(folders)
      assetProgress.finish('素材库已加载')
    } catch (e) {
      assetProgress.fail('素材库加载失败')
      console.error(e)
    } finally {
      setLoadingLibrary(false)
    }
  }, [assetProgress])

  const importFolder = useCallback(async (folderName: string, mode: 'manual' | 'random') => {
    const folderAssets = libraryFolders[folderName] || []
    if (folderAssets.length === 0) return

    // Defensive: warn if importing many assets without voiceover
    if (!voiceoverGenerated && folderAssets.length > 20) {
      const ok = window.confirm(
        `该文件夹有 ${folderAssets.length} 个素材，但尚未生成配音。\n\n` +
        `建议先写文案 → 生成配音 → 确定时长后再导入素材，系统会自动按时长分配。\n\n` +
        `确定现在全部导入吗？`
      )
      if (!ok) return
    }

    // Cap at 50 to prevent explosion
    const capped = folderAssets.slice(0, 50)
    if (folderAssets.length > 50) {
      alert(`素材数量过多（${folderAssets.length} 个），已截取前 50 个导入。`)
    }

    assetProgress.start(`导入 ${Math.min(folderAssets.length, 50)} 个素材...`)
    try {
      await api.importLibraryFolder(folderName, projectId)
      // Backend already updated project.json with correct project-relative paths.
      // Refresh project assets to avoid overwriting with library-relative paths.
      const updated = await api.getProject(projectId)
      if (updated?.assets && onBatchAssetsChange) {
        onBatchAssetsChange(updated.assets)
      }
      setShowLibrary(false)
      assetProgress.finish('素材已导入')
      return
    } catch (err: any) {
      // Backend limit / error: fall back to capped client-side import
      console.warn('Backend folder import failed, falling back:', err)
    }

    const ordered = mode === 'random'
      ? [...capped].sort(() => Math.random() - 0.5)
      : [...capped]
    const uploaded = ordered.map((a: any) => ({
      id: a.id,
      type: a.type,
      name: a.filename,
      path: a.path,
      metadata: { libraryFolder: a.folder || folderName }
    }))
    if (onBatchAssetsChange) onBatchAssetsChange(uploaded)
    setShowLibrary(false)
    assetProgress.finish('素材已导入')
  }, [libraryFolders, projectId, voiceoverGenerated, onBatchAssetsChange, assetProgress])

  const importFromLibrary = useCallback(async (libAsset: any) => {
    assetProgress.start('导入素材...')
    try {
      const r = await api.importLibraryAsset(libAsset.id, projectId)
      if (visualMode === 'single') {
        onAssetChange(r.path, r)
      } else if (onBatchAssetsChange) {
        const imported = { id: libAsset.id, type: libAsset.type, name: libAsset.filename, path: r.path }
        const next = imageAssets.some((asset: any) => asset.path === r.path) ? imageAssets : [...imageAssets, imported]
        onBatchAssetsChange(next)
      }
      setShowLibrary(false)
      assetProgress.finish('素材已导入')
    } catch (e) {
      assetProgress.fail('素材导入失败')
      console.error(e)
    }
  }, [projectId, imageAssets, onAssetChange, onBatchAssetsChange, assetProgress, visualMode])

  const uploadLibraryFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return
    assetProgress.start(`上传 ${files.length} 个素材到素材库...`)
    for (const [idx, f] of Array.from(files).entries()) {
      try {
        assetProgress.set(Math.round((idx / files.length) * 90), `上传 ${idx + 1}/${files.length}`)
        await api.uploadToLibrary(f)
      } catch {
        // Keep going so one bad file does not block the whole batch.
      }
    }
    assetProgress.finish('素材库上传完成')
    await openLibrary()
  }, [assetProgress, openLibrary])

  const handleSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    if (visualMode === 'single' || files.length === 1) {
      const file = files[0]
      if (file.type.startsWith('image/') || (visualMode === 'carousel' && file.type.startsWith('video/'))) {
        assetProgress.start('上传素材...')
        try {
          const r = await api.uploadAsset(projectId, file)
          onAssetChange(r.path, r)
          assetProgress.finish('素材已上传')
        } catch {
          assetProgress.fail('素材上传失败')
        }
      }
      return
    }

    // Multiple files: upload all, store as batch
    const uploaded: any[] = []
    assetProgress.start(`上传 ${files.length} 个素材...`)
    for (let i = 0; i < files.length; i++) {
      const f = files[i]
      if (!f.type.startsWith('image/') && !f.type.startsWith('video/')) continue
      try {
        assetProgress.set(Math.round((i / files.length) * 90), `上传 ${i + 1}/${files.length}`)
        const r = await api.uploadAsset(projectId, f)
        const mediaType = f.type.startsWith('video/') ? 'video' : 'image'
        uploaded.push({
          id: `asset_${mediaType}_${i}`, type: mediaType,
          name: r.filename, path: r.path,
        })
      } catch { /* skip failed */ }
    }
    if (uploaded.length > 0 && onBatchAssetsChange) {
      onBatchAssetsChange(uploaded)
      assetProgress.finish('素材已上传')
    } else {
      assetProgress.fail('没有成功上传的素材')
    }
  }, [projectId, onAssetChange, onBatchAssetsChange, assetProgress, visualMode])

  // Media type icon / label
  const extension = (name: string) => name.split('.').pop()?.toLowerCase() || ''
  const isVideo = (a: any) => a.type === 'video' || ['mp4', 'mov', 'avi', 'mkv', 'webm'].includes(extension(a.name))

  // Drag reorder state
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [overIdx, setOverIdx] = useState<number | null>(null)
  const [inspectedAssetId, setInspectedAssetId] = useState<string | null>(null)

  useEffect(() => {
    if (inspectedAssetId && !imageAssets.some((asset: any) => (asset.id || asset.path) === inspectedAssetId)) {
      setInspectedAssetId(null)
    }
  }, [imageAssets, inspectedAssetId])

  const handleDragStart = useCallback((i: number) => setDragIdx(i), [])
  const handleDragOver = useCallback((e: React.DragEvent, i: number) => { e.preventDefault(); setOverIdx(i) }, [])
  const handleDragEnd = useCallback(() => { setDragIdx(null); setOverIdx(null) }, [])
  const handleReorderDrop = useCallback((e: React.DragEvent, dropIdx: number) => {
    e.preventDefault()
    if (dragIdx === null || dragIdx === dropIdx || !onBatchAssetsChange) return
    const arr = [...imageAssets]
    const [moved] = arr.splice(dragIdx, 1)
    arr.splice(dropIdx, 0, moved)
    onBatchAssetsChange(arr)
    setDragIdx(null)
    setOverIdx(null)
  }, [dragIdx, imageAssets, onBatchAssetsChange])

  // Carousel projects keep their material grid visible even with one source asset.
  if (visualMode === 'carousel' && imageAssets.length > 0) {
    const imgCount = imageAssets.filter(a => !isVideo(a)).length
    const vidCount = imageAssets.filter(a => isVideo(a)).length
    const groupedAssets = imageAssets.reduce((acc: Record<string, any[]>, a: any) => {
      const folder = a.metadata?.libraryFolder
      if (folder) (acc[folder] ||= []).push(a)
      return acc
    }, {})
    return (
      <section className="panel-section">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-primary)' }}>素材</h3>
          <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
            {imageAssets.length} 项{imgCount > 0 ? ` · ${imgCount}图` : ''}{vidCount > 0 ? ` · ${vidCount}视频` : ''}
          </span>
        </div>
        <div className="mb-3">
          <LoadingProgress active={assetProgress.active} progress={assetProgress.progress} label={assetProgress.label} failed={assetProgress.failed} />
        </div>

        {/* 排序模式 + 每张时长 */}
        <div className="flex items-center gap-2 mb-3">
          <button
            onClick={() => {
              if (!voiceoverGenerated) { alert('请先在「文案」Tab 生成配音，系统会根据配音时长自动裁剪素材。'); return }
              onShuffleModeChange?.(true)
            }}
            className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border font-medium transition-all ${
              shuffleMode ? 'selected-surface' : 'hover:opacity-90'
            }`}
            style={shuffleMode ? undefined : { background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
          >
            <Shuffle size={12} weight={shuffleMode ? 'bold' : 'regular'} />
            随机
          </button>
          <button
            onClick={() => {
              if (!voiceoverGenerated) { alert('请先在「文案」Tab 生成配音，系统会根据配音时长自动裁剪素材。'); return }
              onShuffleModeChange?.(false)
            }}
            className={`flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-full border font-medium transition-all ${
              !shuffleMode ? 'selected-surface' : 'hover:opacity-90'
            }`}
            style={!shuffleMode ? undefined : { background: 'var(--bg-surface)', color: 'var(--text-primary)', borderColor: 'var(--border)' }}
          >
            <ListNumbers size={12} weight={!shuffleMode ? 'bold' : 'regular'} />
            顺序
          </button>
          <div className="ml-auto flex items-center gap-1.5">
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>每张</span>
            <input
              type="number"
              min="0.3" max="10" step="0.1"
              value={perImageDuration}
              onChange={(e) => onPerImageDurationChange?.(Number(e.target.value) || 1.0)}
              className="w-14 rounded-md px-1.5 py-0.5 text-[11px] font-mono text-center outline-none transition-colors"
              style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', borderColor: 'var(--border-subtle)', borderWidth: '1px', borderStyle: 'solid' }}
            />
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>秒</span>
          </div>
        </div>

        {onInsertOpeningBlack && (
          <button
            onClick={async () => {
              assetProgress.start('插入片头黑幕...')
              try {
                const ok = await onInsertOpeningBlack()
                if (ok === false) {
                  assetProgress.fail('片头黑幕未插入')
                } else {
                  assetProgress.finish('片头黑幕已插入')
                }
              } catch (err) {
                assetProgress.fail('片头黑幕插入失败')
                console.error(err)
              }
            }}
            disabled={assetProgress.active}
            className="w-full mb-3 text-xs font-medium py-2 rounded-lg transition-all active:scale-[0.98] flex items-center justify-center gap-2"
            style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
          >
              <span className="w-3 h-3 rounded-sm border" style={{ background: 'var(--text-primary)', borderColor: 'var(--border-subtle)' }} />
            开场黑幕 3 秒
          </button>
        )}

        {Object.keys(groupedAssets).length > 0 && (
          <div className="mb-3 space-y-1.5">
            {Object.entries(groupedAssets).map(([folder, items]) => (
              <div key={folder} className="flex items-center gap-2 rounded-lg px-2.5 py-1.5" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                <FolderOpen size={13} style={{ color: 'var(--accent)' }} weight="fill" />
                <span className="text-[11px] font-medium truncate" style={{ color: 'var(--text-primary)' }}>{folder}</span>
                <span className="text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>{items.length} 个</span>
              </div>
            ))}
          </div>
        )}

        {/* Thumbnail grid */}
        <div className="grid grid-cols-3 gap-2 mb-3">
          {imageAssets.slice(0, 9).map((a: any, i: number) => (
            <div
              key={a.id || i}
              draggable
              onDragStart={() => handleDragStart(i)}
              onDragOver={(e) => handleDragOver(e, i)}
              onDragEnd={handleDragEnd}
              onDrop={(e) => handleReorderDrop(e, i)}
              className={`aspect-[3/2] rounded-md overflow-hidden relative group/item cursor-grab active:cursor-grabbing transition-all focus-visible:outline-none ${
                dragIdx === i ? 'opacity-40 scale-95' : ''
              } ${overIdx === i && dragIdx !== null && dragIdx !== i ? 'ring-2 ring-[var(--accent)] ring-offset-1' : ''} ${
                inspectedAssetId === (a.id || a.path) ? 'ring-2 ring-[var(--accent)] ring-offset-1' : ''
              }`}
              style={{ background: 'var(--bg-elevated)' }}
            >
              {isVideo(a) && (
                <button
                  type="button"
                  draggable={false}
                  aria-label={`检查视频素材 ${a.name}`}
                  title="查看素材信息和处理操作"
                  onClick={() => setInspectedAssetId((current) => current === (a.id || a.path) ? null : (a.id || a.path))}
                  className="absolute inset-0 z-10 focus-visible:outline-none"
                />
              )}
              {isVideo(a) ? (
                <div className="w-full h-full flex items-center justify-center" style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)' }}>
                  <Video size={24} weight="fill" className="opacity-50" />
                </div>
              ) : (
                <img
                  src={`/api/projects/${projectId}/assets/stream?path=${encodeURIComponent(a.path)}`}
                  className="w-full h-full object-cover"
                  alt={a.name}
                  onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
              )}
              {/* Delete button per item */}
              <button
                onClick={(event) => {
                  event.stopPropagation()
                  const next = imageAssets.filter((_: any, j: number) => j !== i)
                  onBatchAssetsChange?.(next)
                }}
                className="absolute z-20 top-1 right-1 p-0.5 rounded opacity-0 group-hover/item:opacity-100 focus:opacity-100 transition-opacity shadow-sm"
                style={{ background: 'var(--danger)', color: 'var(--text-inverse)' }}
              >
                <Trash size={10} weight="bold" />
              </button>
              {/* Video badge */}
              {isVideo(a) && (
                <span className="absolute bottom-1 left-1 text-[9px] px-1.5 py-0.5 rounded font-mono" style={{ background: 'rgba(0,0,0,0.58)', color: 'var(--text-primary)' }}>
                  {extension(a.name)}
                </span>
              )}
              {i === 8 && imageAssets.length > 9 && (
                <div className="absolute inset-0 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.46)' }}>
                  <span className="text-xs font-bold" style={{ color: 'var(--text-primary)' }}>+{imageAssets.length - 9}</span>
                </div>
              )}
            </div>
          ))}
        </div>

        {(() => {
          const inspectedAsset = imageAssets.find((asset: any) => (asset.id || asset.path) === inspectedAssetId && isVideo(asset))
          return inspectedAsset ? (
            <MediaAssetInspector
              projectId={projectId}
              asset={inspectedAsset}
              onProjectRefresh={onProjectRefresh || (async () => {})}
            />
          ) : null
        })()}

        {/* 生成轮播按钮 */}
        {onGenerateCarousel && imageAssets.length >= 2 && (
          <button
            onClick={async () => {
              assetProgress.start('生成轮播...')
              try {
                const ok = await onGenerateCarousel()
                if (ok === false) {
                  assetProgress.fail('轮播未生成')
                } else {
                  assetProgress.finish('轮播已生成')
                }
              } catch (err) {
                assetProgress.fail('轮播生成失败')
                console.error(err)
              }
            }}
            disabled={!voiceoverGenerated || assetProgress.active}
                    className="w-full mb-3 text-xs font-medium py-2 rounded-lg transition-all active:scale-[0.98] shadow-sm"
                    style={voiceoverGenerated
              ? { background: 'var(--accent)', color: 'var(--accent-contrast)', opacity: 1, cursor: 'pointer' }
              : { background: 'var(--bg-elevated)', color: 'var(--text-muted)', opacity: 0.6, cursor: 'not-allowed' }
            }
          >
            {voiceoverGenerated
              ? `生成轮播 · 按配音时长填满 ${imageAssets.length} 个素材`
              : `请先生成配音 · ${imageAssets.length} 个素材待分配`
            }
          </button>
        )}

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <label className="flex items-center gap-2 cursor-pointer group">
              <div className="w-8 h-8 rounded-lg flex items-center justify-center transition-all group-hover:opacity-80" style={{ background: 'var(--bg-elevated)' }}>
                <FolderOpen size={14} style={{ color: 'var(--text-muted)' }} />
              </div>
              <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>添加素材</span>
              <input
                type="file" accept={ACCEPT_TYPES} multiple
                onChange={handleSelect}
                className="hidden"
                /* @ts-ignore */
                webkitdirectory=""
              />
            </label>
            <button
              onClick={openLibrary}
              className="flex items-center gap-1 text-[11px] font-medium transition-all hover:opacity-80"
              style={{ color: 'var(--accent)' }}
            >
              从素材库
            </button>
          </div>
          <button
            onClick={() => onBatchAssetsChange?.([])}
            className="flex items-center gap-1 text-[11px] text-red-500 hover:text-red-700 font-medium transition-colors"
          >
            <Trash size={12} weight="bold" />
            清空
          </button>
        </div>
      </section>
    )
  }

  // Single-mode projects can keep many candidates, but only one is active on the timeline.
  const selectedAsset = imageAssets.find((asset: any) => asset.path === assetPath)
  const singleIsVideo = !!assetPath && (selectedAsset ? isVideo(selectedAsset) : isVideo({ name: assetPath.split(/[\\/]/).pop() || '' }))
  const singleCandidates = imageAssets.filter((asset: any) => !isVideo(asset))
  return (
    <section
      className="panel-section"
      onDrop={handleDrop}
      onDragOver={(e) => e.preventDefault()}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-primary)' }}>
          {visualMode === 'single' ? '单图贯穿' : '轮播素材'}
        </h3>
        <span className="status-pill px-2 py-1 text-[10px]" data-tone={assetPath ? 'ok' : 'warn'}>
          {assetPath ? '已选择' : '待选择'}
        </span>
      </div>
      <div className="mb-3">
        <LoadingProgress active={assetProgress.active} progress={assetProgress.progress} label={assetProgress.label} failed={assetProgress.failed} />
      </div>
      {assetPath ? (
        <div className="relative group rounded-lg overflow-hidden" style={{ borderColor: 'var(--border-subtle)', borderWidth: '1px', borderStyle: 'solid', background: 'var(--bg-elevated)' }}>
          <div className="aspect-video flex items-center justify-center overflow-hidden" style={{ background: 'var(--bg-surface)' }}>
            {singleIsVideo ? (
              <Video size={32} style={{ color: 'var(--text-muted)' }} weight="fill" />
            ) : (
              <img
                src={`/api/projects/${projectId}/assets/stream?path=${encodeURIComponent(assetPath)}`}
                className="w-full h-full object-cover"
                alt="封面"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = 'none'
                  ;(e.target as HTMLImageElement).parentElement!.innerHTML =
                    '<div class="flex items-center justify-center h-full text-xs" style="color:var(--text-muted)">加载失败</div>'
                }}
              />
            )}
          </div>
              <div className="absolute inset-0 transition-colors" style={{ background: 'transparent' }} />
              <button
                onClick={() => onAssetChange('')}
                aria-label="移除当前图片"
                title="移除当前图片"
            className="absolute top-2 right-2 p-1.5 rounded-md opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
            style={{ background: 'var(--danger)', color: 'var(--text-inverse)' }}
              >
                <Trash size={14} weight="bold" />
              </button>
          <div className="absolute bottom-0 left-0 right-0 px-3 py-2 border-t" style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-subtle)' }}>
            <div className="flex items-center gap-2">
              <p className="text-[11px] truncate" style={{ color: 'var(--text-secondary)' }}>{assetPath.split(/[\\/]/).pop()}</p>
              {visualMode === 'single' && <span className="ml-auto text-[10px] shrink-0" style={{ color: 'var(--accent)' }}>贯穿全片</span>}
            </div>
          </div>
        </div>
      ) : (
        <label
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          className="flex flex-col items-center justify-center aspect-video border-2 border-dashed rounded-lg cursor-pointer transition-all group hover:opacity-80"
          style={{ borderColor: 'var(--border)' }}
        >
          <input type="file" accept={acceptedTypes} multiple={visualMode === 'carousel'} onChange={handleSelect} className="hidden" />
          <div className="w-10 h-10 rounded-full flex items-center justify-center mb-2 transition-all group-hover:opacity-80" style={{ background: 'var(--bg-elevated)' }}>
            <UploadSimple size={20} style={{ color: 'var(--text-muted)' }} />
          </div>
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>拖拽或点击上传</span>
          <span className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
            {visualMode === 'single' ? '选择一张图片' : '支持图片和视频'}
          </span>
          <button
            onClick={(e) => { e.preventDefault(); openLibrary() }}
            className="mt-2 text-[11px] font-medium transition-all hover:opacity-80"
            style={{ color: 'var(--accent)' }}
          >
            或从素材库选择
          </button>
        </label>
      )}

      {assetPath && (
        <div className="flex gap-2 mt-3">
          <label className="btn-cinematic flex-1 flex items-center justify-center gap-1.5 text-[11px] cursor-pointer">
            <UploadSimple size={13} weight="bold" />
            替换图片
            <input type="file" accept={acceptedTypes} onChange={handleSelect} className="hidden" />
          </label>
          <button onClick={openLibrary} className="btn-cinematic flex-1 flex items-center justify-center gap-1.5 text-[11px]">
            <FolderOpen size={13} weight="bold" />
            从素材库
          </button>
        </div>
      )}

      {visualMode === 'single' && singleCandidates.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>项目内图片</span>
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>{singleCandidates.length} 张</span>
          </div>
          <div className="grid grid-cols-4 gap-2 max-h-40 overflow-y-auto pr-1">
            {singleCandidates.map((asset: any) => {
              const selected = asset.path === assetPath
              return (
                <button
                  key={asset.id || asset.path}
                  onClick={() => onAssetChange(asset.path, asset)}
                  className="aspect-square rounded-md overflow-hidden border-2 transition-all relative"
                  style={{ borderColor: selected ? 'var(--accent)' : 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
                  title={asset.name}
                >
                  <img
                    src={`/api/projects/${projectId}/assets/stream?path=${encodeURIComponent(asset.path)}`}
                    className="w-full h-full object-cover"
                    alt={asset.name}
                  />
                  {selected && (
                    <span className="absolute bottom-1 left-1 right-1 text-[9px] py-0.5 rounded" style={{ background: 'var(--accent)', color: 'var(--accent-contrast)' }}>
                      当前画面
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      {onInsertOpeningBlack && (
        <button
          onClick={async () => {
            assetProgress.start('插入片头黑幕...')
            try {
              const ok = await onInsertOpeningBlack()
              if (ok === false) assetProgress.fail('片头黑幕未插入')
              else assetProgress.finish('片头黑幕已插入')
            } catch (err) {
              assetProgress.fail('片头黑幕插入失败')
              console.error(err)
            }
          }}
          disabled={assetProgress.active}
          className="w-full mt-3 text-xs font-medium py-2 rounded-lg transition-all active:scale-[0.98] flex items-center justify-center gap-2"
          style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
        >
          <span className="w-3 h-3 rounded-sm border" style={{ background: '#000000', borderColor: 'var(--border)' }} />
          开场黑幕 3 秒
        </button>
      )}

      {/* Library Picker Modal */}
      {showLibrary && (
        <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.4)' }} onClick={() => setShowLibrary(false)}>
          <div className="rounded-lg shadow-lg w-[600px] max-h-[70vh] overflow-hidden glass-panel" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex items-center gap-2">
                {selectedFolder && (
                  <button onClick={() => setSelectedFolder(null)} className="p-1 rounded-md hover:opacity-70" style={{ color: 'var(--text-secondary)' }} title="返回文件夹列表">
                    <ArrowLeft size={16} weight="bold" />
                  </button>
                )}
                <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                  {selectedFolder ? `${visualMode === 'single' ? '选择图片' : '选择模式'} — ${selectedFolder}` : '素材库'}
                </h3>
              </div>
              <button onClick={() => { setShowLibrary(false); setSelectedFolder(null); setImportMode(null) }}
                className="p-1 rounded-md" style={{ color: 'var(--text-secondary)' }} aria-label="关闭素材库" title="关闭素材库">
                <X size={18} weight="bold" />
              </button>
            </div>
            <div className="px-4 pt-3">
              <LoadingProgress active={assetProgress.active} progress={assetProgress.progress} label={assetProgress.label} failed={assetProgress.failed} />
            </div>
            <div className="p-4 overflow-y-auto max-h-[55vh]">
              {loadingLibrary ? (
                <p className="text-center text-sm py-8" style={{ color: 'var(--text-muted)' }}>加载中…</p>
              ) : selectedFolder ? (
                visualMode === 'single' ? (
                  <div className="grid grid-cols-4 gap-2">
                    {(libraryFolders[selectedFolder] || []).filter((asset: any) => asset.type === 'image').map((asset: any) => (
                      <button
                        key={asset.id}
                        onClick={() => importFromLibrary(asset)}
                        className="aspect-square rounded-lg overflow-hidden border transition-all relative group"
                        style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-subtle)' }}
                        title={asset.filename}
                      >
                        <img src={`/api/library/raw/${asset.stored_name}`} className="w-full h-full object-cover" loading="lazy" alt={asset.filename} />
                        <span className="absolute bottom-1 left-1 right-1 text-[9px] py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity"
                          style={{ background: 'var(--accent)', color: 'var(--accent-contrast)' }}>
                          选为贯穿图
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-6 space-y-4">
                    <FolderOpen size={36} className="mx-auto" style={{ color: 'var(--accent)' }} weight="fill" />
                    <p className="text-sm" style={{ color: 'var(--text-primary)' }}>
                      {libraryFolders[selectedFolder]?.length || 0} 个素材
                    </p>
                    <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      选择导入模式：
                    </p>
                    <div className="flex gap-3 justify-center">
                      <button onClick={() => importFolder(selectedFolder, 'random')}
                        className="btn-gold px-6 py-2.5 text-sm">
                        随机排列
                      </button>
                      <button onClick={() => importFolder(selectedFolder, 'manual')}
                        className="btn-cinematic px-6 py-2.5 text-sm">
                        顺序导入
                      </button>
                    </div>
                  </div>
                )
              ) : libraryAssets.length === 0 ? (
                <div className="text-center py-6">
                  <FolderOpen size={32} className="mx-auto mb-2" style={{ color: 'var(--text-muted)' }} />
                  <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>素材库为空</p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>先去素材库页面上传，或在这里直接上传</p>
                  <label className="btn-gold inline-flex items-center gap-2 cursor-pointer mt-4">
                    <UploadSimple size={14} weight="bold" />
                    上传到素材库
                    <input
                      type="file" multiple accept="image/*,video/*,audio/*"
                      className="hidden"
                      onChange={async (e) => {
                        await uploadLibraryFiles(e.target.files)
                        e.target.value = ''
                      }}
                    />
                  </label>
                </div>
              ) : (
                <div className="space-y-2">
                  {/* Upload entry in modal */}
                  <label className="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg cursor-pointer transition-all hover:opacity-80 mb-2"
                    style={{ background: 'var(--bg-elevated)', border: '1px dashed var(--border)' }}>
                    <UploadSimple size={15} style={{ color: 'var(--accent)' }} weight="bold" />
                    <span className="text-[11px] font-medium" style={{ color: 'var(--text-primary)' }}>上传到素材库</span>
                    <span className="text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>图片/视频/音频</span>
                    <input
                      type="file" multiple accept="image/*,video/*,audio/*"
                      className="hidden"
                      onChange={async (e) => {
                        await uploadLibraryFiles(e.target.files)
                        e.target.value = ''
                      }}
                    />
                  </label>
                  {/* Folder list */}
                  {Object.keys(libraryFolders).map(folder => (
                    <button key={folder}
                      onClick={() => setSelectedFolder(folder)}
                      className="w-full flex items-center gap-3 px-4 py-3 rounded-lg transition-all hover:opacity-80"
                      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)' }}>
                      <FolderOpen size={18} style={{ color: 'var(--accent)' }} weight="fill" />
                      <span className="text-sm font-heading font-medium" style={{ color: 'var(--text-primary)' }}>{folder}</span>
                      <span className="text-[10px] ml-auto" style={{ color: 'var(--text-muted)' }}>{libraryFolders[folder].length} 个</span>
                    </button>
                  ))}
                  {/* Loose files */}
                  {libraryAssets.filter(a => !a.folder && (visualMode !== 'single' || a.type === 'image')).length > 0 && (
                    <>
                      <p className="text-[10px] uppercase tracking-wider pt-2" style={{ color: 'var(--text-muted)' }}>未分组素材</p>
                      <div className="grid grid-cols-4 gap-2">
                        {libraryAssets.filter(a => !a.folder && (visualMode !== 'single' || a.type === 'image')).map((a: any) => (
                          <button key={a.id} onClick={() => importFromLibrary(a)}
                            className="aspect-square rounded-lg overflow-hidden border transition-all relative group"
                            style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-subtle)' }}>
                            {a.type === 'image' ? (
                              <img src={`/api/library/raw/${a.stored_name}`} className="w-full h-full object-cover" loading="lazy" />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center" style={{ background: 'var(--bg-surface)' }}>
                                <Video size={20} style={{ color: 'var(--text-muted)' }} weight="fill" />
                              </div>
                            )}
                            <div className="absolute inset-0 transition-colors flex items-center justify-center" style={{ background: 'rgba(0,0,0,0)' }}>
                              <span className="text-[10px] font-bold opacity-0 group-hover:opacity-100 px-2 py-1 rounded"
                                style={{ background: 'var(--accent)', color: 'var(--accent-contrast)' }}>选择</span>
                            </div>
                          </button>
                        ))}
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </section>
  )
}

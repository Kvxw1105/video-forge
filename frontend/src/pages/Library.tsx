import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { House, UploadSimple, Trash, Image as ImageIcon, VideoCamera, MusicNotes, FolderOpen, CaretDown, CaretRight, CheckSquare, Square, X } from '@phosphor-icons/react'
import { api } from '../lib/api'
import { useProgress, LoadingProgress } from '../hooks/useProgress'

const TYPE_TONE: Record<string, 'ok' | 'warn' | 'danger'> = {
  image: 'ok',
  video: 'danger',
  audio: 'warn',
}

export default function Library() {
  const navigate = useNavigate()
  const [assets, setAssets] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [filter, setFilter] = useState<string>('all')
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(new Set())
  // Selection mode
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)
  const pageProgress = useProgress()

  const load = useCallback(async () => {
    setLoading(true)
    pageProgress.start('加载素材库...')
    try {
      const list = await api.listLibrary()
      setAssets(list)
      pageProgress.finish('素材库已加载')
    } catch (e) {
      pageProgress.fail('素材库加载失败')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [pageProgress.start, pageProgress.finish, pageProgress.fail])

  useEffect(() => { load() }, [load])

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return
    setUploading(true)
    pageProgress.start(`上传 ${files.length} 个素材...`)
    try {
      for (const [idx, file] of Array.from(files).entries()) {
        pageProgress.set(Math.round((idx / files.length) * 90), `上传 ${idx + 1}/${files.length}`)
        await api.uploadToLibrary(file)
      }
      await load()
      pageProgress.finish('上传完成')
    } catch (e) {
      pageProgress.fail('上传失败')
      console.error(e)
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`确定删除「${name}」？`)) return
    pageProgress.start('删除素材...')
    try {
      await api.deleteLibraryAsset(id)
      setAssets(prev => prev.filter(a => a.id !== id))
      setSelected(prev => { const n = new Set(prev); n.delete(id); return n })
      pageProgress.finish('删除完成')
    } catch (e) {
      pageProgress.fail('删除失败')
      console.error(e)
    }
  }

  const toggleSelect = (id: string) => {
    setSelected(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const selectAll = () => {
    const visible = getVisibleIds()
    setSelected(new Set(visible))
  }

  const deselectAll = () => setSelected(new Set())

  const deleteSelected = async () => {
    if (selected.size === 0) return
    if (!confirm(`确定删除选中的 ${selected.size} 个素材？`)) return
    setDeleting(true)
    pageProgress.start(`删除 ${selected.size} 个素材...`)
    try {
      const ids = Array.from(selected)
      for (const [idx, id] of ids.entries()) {
        pageProgress.set(Math.round((idx / ids.length) * 90), `删除 ${idx + 1}/${ids.length}`)
        await api.deleteLibraryAsset(id)
      }
      setAssets(prev => prev.filter(a => !selected.has(a.id)))
      setSelected(new Set())
      setSelectMode(false)
      pageProgress.finish('删除完成')
    } catch (e) {
      pageProgress.fail('删除失败')
      console.error(e)
    } finally {
      setDeleting(false)
    }
  }

  const deleteAll = async () => {
    if (!confirm(`确定删除全部 ${assets.length} 个素材？此操作不可恢复。`)) return
    setDeleting(true)
    pageProgress.start(`清空 ${assets.length} 个素材...`)
    try {
      for (const [idx, a] of assets.entries()) {
        pageProgress.set(Math.round((idx / assets.length) * 90), `删除 ${idx + 1}/${assets.length}`)
        await api.deleteLibraryAsset(a.id)
      }
      setAssets([])
      setSelected(new Set())
      setSelectMode(false)
      pageProgress.finish('已清空素材库')
    } catch (e) {
      pageProgress.fail('清空失败')
      console.error(e)
    } finally {
      setDeleting(false)
    }
  }

  const getVisibleIds = () => {
    const { folders, loose } = grouped()
    const ids: string[] = []
    for (const folderAssets of Object.values(folders)) {
      for (const a of folderAssets) ids.push(a.id)
    }
    for (const a of loose) ids.push(a.id)
    return ids
  }

  // Group assets by folder (top-level folder only for grouping)
  const grouped = useCallback(() => {
    let filtered: any[]
    if (filter === 'all') filtered = assets
    else if (filter === 'folder') filtered = assets.filter(a => a.folder)
    else filtered = assets.filter(a => a.type === filter)
    const folders: Record<string, any[]> = {}
    const loose: any[] = []
    for (const a of filtered) {
      const folder = a.folder || ''
      if (folder) {
        // Group by top-level folder (first segment before /)
        const topFolder = folder.split('/')[0]
        if (!folders[topFolder]) folders[topFolder] = []
        folders[topFolder].push(a)
      } else {
        loose.push(a)
      }
    }
    return { folders, loose }
  }, [assets, filter])

  const toggleFolder = (name: string) => {
    setExpandedFolders(prev => {
      const n = new Set(prev)
      if (n.has(name)) n.delete(name)
      else n.add(name)
      return n
    })
  }

  const { folders, loose } = grouped()
  const folderNames = Object.keys(folders).sort()
  const counts = {
    all: assets.length,
    image: assets.filter(a => a.type === 'image').length,
    video: assets.filter(a => a.type === 'video').length,
    audio: assets.filter(a => a.type === 'audio').length,
  }

  return (
    <div className="min-h-[100dvh] workbench-shell">
      {/* Header */}
      <header className="min-h-14 toolbar-glass border-b flex flex-wrap items-center justify-between gap-2 px-3 md:px-6 py-2 shrink-0" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center gap-3">
          <button onClick={() => navigate('/')} className="flex items-center gap-2 hover:opacity-80 transition-opacity">
            <div className="w-7 h-7 rounded-sm flex items-center justify-center" style={{ background: 'var(--accent-bg)', border: '1px solid var(--border-accent)' }}>
              <FolderOpen size={15} style={{ color: 'var(--accent)' }} weight="fill" />
            </div>
            <div>
              <h1 className="text-sm font-heading font-semibold leading-tight tracking-[0.12em]" style={{ color: 'var(--text-primary)' }}>素材库</h1>
              <p className="text-[10px] leading-tight" style={{ color: 'var(--text-muted)' }}>{assets.length} 个素材 · {folderNames.length} 个文件夹</p>
            </div>
          </button>
          <div className="w-px h-5" style={{ background: 'var(--border-subtle)' }} />
          <button onClick={() => navigate('/')} className="btn-cinematic flex items-center gap-1.5 text-[11px] px-2 py-1">
            <House size={13} weight="bold" /> 首页
          </button>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2">
          {selectMode ? (
            <>
              <span className="status-pill px-2 py-1 text-[10px] font-mono">{selected.size} 已选</span>
              <button onClick={selectAll} className="btn-cinematic text-[10px] px-2 py-1">全选</button>
              <button onClick={deselectAll} className="btn-cinematic text-[10px] px-2 py-1">取消</button>
              <button onClick={deleteSelected} disabled={selected.size === 0 || deleting}
                className="status-pill px-3 py-1.5 text-[10px] font-semibold transition-all disabled:opacity-40" data-tone="danger">
                {deleting ? '删除中…' : `删除 ${selected.size} 个`}
              </button>
              <button onClick={() => { setSelectMode(false); setSelected(new Set()) }}
                className="icon-button w-7 h-7 min-w-0 min-h-0">
                <X size={14} />
              </button>
            </>
          ) : (
            <>
              {assets.length > 0 && (
                <button onClick={() => setSelectMode(true)}
                  className="btn-cinematic text-[10px] flex items-center gap-1">
                  <CheckSquare size={12} /> 选择
                </button>
              )}
              <label className="btn-gold flex items-center gap-2 cursor-pointer">
                <UploadSimple size={14} weight="bold" />
                {uploading ? '上传中…' : '上传文件'}
                <input type="file" multiple accept="image/*,video/*,audio/*" className="hidden" onChange={(e) => handleUpload(e.target.files)} disabled={uploading} />
              </label>
              <label className="btn-cinematic flex items-center gap-2 cursor-pointer">
                <FolderOpen size={14} weight="bold" />
                {uploading ? '上传中…' : '上传文件夹'}
                {/* @ts-ignore */}
                <input type="file" webkitdirectory="" multiple className="hidden" onChange={(e) => handleUpload(e.target.files)} disabled={uploading} />
              </label>
              {assets.length > 0 && (
                <button onClick={deleteAll} disabled={deleting}
                  className="status-pill px-3 py-1.5 text-[10px] font-semibold transition-all disabled:opacity-40" data-tone="danger">
                  <Trash size={12} className="inline mr-1" />清空
                </button>
              )}
            </>
          )}
        </div>
      </header>
      {pageProgress.active && (
        <div className="max-w-6xl mx-auto px-6 pt-3">
          <LoadingProgress active={pageProgress.active} progress={pageProgress.progress} label={pageProgress.label} failed={pageProgress.failed} />
        </div>
      )}

      {/* Filter tabs */}
      <div className="max-w-6xl mx-auto px-6 pt-5">
        <div className="flex gap-1.5">
          {(['all', 'folder', 'image', 'video', 'audio'] as const).map(type => {
            const labels: Record<string, string> = { all: '全部', folder: '文件夹', image: '图片', video: '视频', audio: '音频' }
            const c = type === 'folder' ? folderNames.length : counts[type] || 0
            return (
              <button key={type} onClick={() => setFilter(type)}
                className={`px-3 py-1.5 rounded text-[11px] font-heading font-semibold tracking-wide transition-all ${
                  filter === type ? 'selected-surface' : 'btn-cinematic'
                }`}>
                {labels[type]}
                <span className="ml-1 opacity-60">{c}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Content */}
      <main className="max-w-6xl mx-auto px-6 py-5">
        {loading ? (
          <div className="text-center py-20 text-sm font-heading italic" style={{ color: 'var(--text-muted)' }}>加载中…</div>
        ) : assets.length === 0 ? (
          <div className="text-center py-20">
            <FolderOpen size={48} className="mx-auto mb-4" style={{ color: 'var(--text-muted)' }} />
            <p className="text-sm mb-1 font-heading" style={{ color: 'var(--text-secondary)' }}>素材库是空的</p>
            <p className="text-xs italic" style={{ color: 'var(--text-muted)' }}>上传文件夹，素材按文件夹分组管理</p>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Folders */}
            {folderNames.map(folder => {
              const folderAssets = folders[folder]
              const expanded = expandedFolders.has(folder)
              const folderSelected = folderAssets.every(a => selected.has(a.id))
              return (
                <div key={folder} className="card-cinematic overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-3">
                    <button onClick={() => toggleFolder(folder)} className="flex items-center gap-3 flex-1 text-left hover:opacity-80 transition-opacity">
                      {expanded ? <CaretDown size={14} style={{ color: 'var(--text-muted)' }} /> : <CaretRight size={14} style={{ color: 'var(--text-muted)' }} />}
                      <FolderOpen size={18} style={{ color: 'var(--accent)' }} weight="fill" />
                      <span className="text-sm font-heading font-medium" style={{ color: 'var(--text-primary)' }}>{folder}</span>
                      <span className="text-[10px] italic" style={{ color: 'var(--text-muted)' }}>{folderAssets.length} 个素材</span>
                    </button>
                    {selectMode && (
                      <button onClick={() => {
                        if (folderSelected) {
                          setSelected(prev => { const n = new Set(prev); folderAssets.forEach(a => n.delete(a.id)); return n })
                        } else {
                          setSelected(prev => { const n = new Set(prev); folderAssets.forEach(a => n.add(a.id)); return n })
                        }
                      }} className="text-[10px] transition-colors" style={{ color: 'var(--accent)' }}>
                        {folderSelected ? '取消选择' : '全选此文件夹'}
                      </button>
                    )}
                  </div>
                  {expanded && (
                    <div className="px-4 pb-3 grid grid-cols-4 sm:grid-cols-5 md:grid-cols-6 gap-2 border-t pt-3" style={{ borderColor: 'var(--border-subtle)' }}>
                      {folderAssets.map((asset: any) => (
                        <AssetThumb key={asset.id} asset={asset} onDelete={handleDelete}
                          selectMode={selectMode} selected={selected.has(asset.id)} onToggleSelect={() => toggleSelect(asset.id)} />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}

            {/* Loose files */}
            {loose.length > 0 && (
              <div>
                {folderNames.length > 0 && <p className="label-cinematic mb-2">未分组素材</p>}
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                  {loose.map((asset: any) => (
                    <AssetThumb key={asset.id} asset={asset} onDelete={handleDelete}
                      selectMode={selectMode} selected={selected.has(asset.id)} onToggleSelect={() => toggleSelect(asset.id)} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

function AssetThumb({ asset, onDelete, selectMode, selected, onToggleSelect }: {
  asset: any; onDelete: (id: string, name: string) => void;
  selectMode: boolean; selected: boolean; onToggleSelect: () => void;
}) {
  const tone = TYPE_TONE[asset.type] || 'warn'
  const ext = (asset.filename || '').split('.').pop()?.toLowerCase() || ''
  const sizeLabel = asset.size > 1024 * 1024
    ? `${(asset.size / 1024 / 1024).toFixed(1)} MB`
    : `${(asset.size / 1024).toFixed(0)} KB`
  const imported = asset.imported_at
    ? new Date(asset.imported_at).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
    : ''
  return (
    <motion.div layout
      className={`group relative card-cinematic overflow-hidden transition-all ${selected ? 'selected-surface' : ''}`}>
      <div className="aspect-square flex items-center justify-center relative overflow-hidden" onClick={selectMode ? onToggleSelect : undefined}>
        {asset.type === 'image' ? (
          <img src={`/api/library/raw/${asset.stored_name}`} alt={asset.filename} className="w-full h-full object-cover opacity-90 transition-opacity" loading="lazy" decoding="async" />
        ) : asset.type === 'video' ? (
          <video src={`/api/library/raw/${asset.stored_name}`} className="w-full h-full object-cover opacity-90" muted preload="none"
            onMouseEnter={(e) => { (e.target as HTMLVideoElement).play().catch(() => {}) }}
            onMouseLeave={(e) => { (e.target as HTMLVideoElement).pause(); (e.target as HTMLVideoElement).currentTime = 0 }} />
        ) : (
          <div className="flex flex-col items-center gap-1">
            <MusicNotes size={24} style={{ color: 'var(--accent)' }} />
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>{sizeLabel}</span>
          </div>
        )}
        <div className="absolute top-1.5 left-1.5 flex items-center gap-1">
          <div className="status-pill text-[8px] px-1.5 py-0.5 rounded font-heading font-semibold tracking-wider uppercase" data-tone={tone}>{asset.type}</div>
          {ext && ext !== asset.type && (
            <div className="status-pill text-[8px] px-1.5 py-0.5 rounded font-mono uppercase">{ext}</div>
          )}
        </div>
        {selectMode ? (
          <div className={`absolute top-1.5 right-1.5 w-5 h-5 rounded flex items-center justify-center transition-all ${
            selected ? 'selected-surface' : 'status-pill'
          }`} style={selected ? undefined : { color: 'var(--text-secondary)' }}>
            {selected ? <CheckSquare size={13} weight="fill" /> : <Square size={13} />}
          </div>
        ) : (
          <button onClick={(e) => { e.stopPropagation(); onDelete(asset.id, asset.filename) }}
            className="absolute top-1.5 right-1.5 icon-button w-5 h-5 min-w-0 min-h-0 opacity-0 group-hover:opacity-100 transition-all"
            style={{ color: 'var(--danger)' }}>
            <Trash size={10} weight="bold" />
          </button>
        )}
      </div>
      <div className="px-2 py-1.5" onClick={selectMode ? onToggleSelect : undefined}>
        <p className="text-[10px] font-heading truncate" style={{ color: 'var(--text-secondary)' }} title={asset.filename}>{asset.filename}</p>
        <div className="flex items-center justify-between mt-0.5">
          <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>{sizeLabel}</span>
          {imported && <span className="text-[9px] font-mono" style={{ color: 'var(--text-muted)' }}>{imported}</span>}
        </div>
      </div>
    </motion.div>
  )
}

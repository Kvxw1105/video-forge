import { useNavigate } from 'react-router-dom'
import { FilmSlate, DownloadSimple, ArrowRight, CheckCircle, WarningCircle, BookmarkSimple, House, Sun, Moon, CircleNotch } from '@phosphor-icons/react'
import { useTheme } from '../../contexts/ThemeContext'

interface JianyingStatus {
  detected: boolean
  path: string | null
  drafts: { name: string; folder: string }[]
}

export default function TopBar({
  projectName, onExportZip, onExportDirect, onSaveTemplate, exporting, exportReady, jianyingStatus,
  saveStatus = 'saved', readinessLabel = exportReady ? '可导出' : '未就绪', readinessTone = exportReady ? 'ok' : 'warn'
}: {
  projectName: string
  onExportZip: () => void
  onExportDirect: () => void
  onSaveTemplate?: () => void
  exporting: boolean
  exportReady: boolean
  jianyingStatus: JianyingStatus | null
  saveStatus?: 'idle' | 'saving' | 'saved' | 'error'
  readinessLabel?: string
  readinessTone?: 'ok' | 'warn' | 'danger'
}) {
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()
  const saveTone = saveStatus === 'error' ? 'danger' : saveStatus === 'saving' ? 'warn' : 'ok'
  const saveLabel = saveStatus === 'saving' ? '保存中' : saveStatus === 'error' ? '保存失败' : '已保存'
  const directExportTitle = !exportReady
    ? readinessLabel
    : !jianyingStatus?.detected
      ? '未检测到剪映草稿目录'
      : '导出到剪映草稿箱'

  return (
    <header className="min-h-14 border-b flex flex-wrap items-center justify-between gap-2 px-3 xl:px-5 py-2 shrink-0 z-10 toolbar-glass">
      {/* Left: brand + back */}
      <div className="flex items-center gap-3">
        <button onClick={() => navigate('/')} className="flex items-center gap-2.5 hover:opacity-80 transition-opacity" title="返回项目列表">
          <div className="w-7 h-7 rounded-sm flex items-center justify-center" style={{ background: 'var(--accent-bg)', border: '1px solid var(--border-accent)' }}>
            <FilmSlate size={15} style={{ color: 'var(--accent)' }} weight="fill" />
          </div>
          <div>
            <h1 className="text-sm font-heading font-semibold leading-tight tracking-[0.08em]" style={{ color: 'var(--text-primary)' }}>
              Video<span style={{ color: 'var(--accent)' }}>Forge</span>
              <span className="hidden 2xl:inline ml-1.5 text-[10px]" style={{ color: 'var(--text-muted)', fontWeight: 500 }}>让表达更好发生</span>
            </h1>
            <p className="text-[10px] truncate max-w-[240px] leading-tight" style={{ color: 'var(--text-secondary)' }}>{projectName}</p>
          </div>
        </button>

        <div className="w-px h-5" style={{ background: 'var(--border-subtle)' }} />

        <button onClick={() => navigate('/')}
          className="flex items-center gap-1.5 text-[11px] transition-colors px-2 py-1 rounded"
          style={{ color: 'var(--text-secondary)' }}
          title="返回首页">
          <House size={13} weight="bold" />
          首页
        </button>
      </div>

      {/* Right: theme toggle + export + status */}
      <div className="flex items-center gap-2">
        <span className="hidden xl:inline-flex status-pill px-2.5 py-1 text-[10px]" data-tone={saveTone} title={saveLabel}>
          {saveStatus === 'saving' ? <CircleNotch size={11} className="animate-spin" weight="bold" /> : saveStatus === 'error' ? <WarningCircle size={11} weight="fill" /> : <CheckCircle size={11} weight="fill" />}
          {saveLabel}
        </span>
        <span className="hidden 2xl:inline-flex status-pill px-2.5 py-1 text-[10px]" data-tone={readinessTone} title={readinessLabel}>
          {exportReady ? <CheckCircle size={11} weight="fill" /> : <WarningCircle size={11} weight="fill" />}
          {readinessLabel}
        </span>
        <button onClick={toggle} className="btn-cinematic p-1.5" title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}>
          {theme === 'dark' ? <Sun size={14} weight="bold" /> : <Moon size={14} weight="bold" />}
        </button>
        {/* 剪映路径状态 */}
        <div className="hidden 2xl:flex status-pill px-2.5 py-1 text-[10px]" data-tone={jianyingStatus?.detected ? 'ok' : jianyingStatus === null ? 'warn' : 'danger'}>
          {jianyingStatus === null ? (
            <><CircleNotch size={11} className="animate-spin" weight="bold" /><span>剪映检测中</span></>
          ) : jianyingStatus.detected ? (
            <>
              <CheckCircle size={11} style={{ color: 'var(--success)' }} weight="fill" />
              <span className="max-w-[180px] truncate" style={{ color: 'var(--text-secondary)' }} title={jianyingStatus.path || ''}>
                剪映：{jianyingStatus.path?.split('com.lveditor.draft')[0]?.replace(/\/User Data\/Projects$/, '').split('\\').pop() || '已检测'}
              </span>
            </>
          ) : (
            <>
              <WarningCircle size={11} style={{ color: 'var(--danger)' }} weight="fill" />
              <span>未检测到剪映</span>
            </>
          )}
        </div>

        {/* Direct export → 剪映 */}
        <button onClick={onExportDirect} disabled={exporting || !exportReady || !jianyingStatus?.detected}
          className="hidden xl:flex btn-cinematic items-center gap-1.5 text-xs disabled:opacity-40" title={directExportTitle}>
          <ArrowRight size={14} weight="bold" />
          {exporting ? '导出中…' : '导出到剪映'}
        </button>

        {/* ZIP download */}
        <button onClick={onExportZip} disabled={exporting || !exportReady}
          className="btn-gold flex items-center gap-1.5 text-xs disabled:opacity-40">
          <DownloadSimple size={14} weight="bold" />
          {exporting ? '导出中…' : '下载 ZIP'}
        </button>

        {/* Save as template */}
        {onSaveTemplate && (
          <button onClick={onSaveTemplate}
            className="hidden 2xl:flex btn-cinematic items-center gap-1.5 text-xs" title="保存为模板">
            <BookmarkSimple size={14} weight="bold" />
            存为模板
          </button>
        )}
      </div>
    </header>
  )
}

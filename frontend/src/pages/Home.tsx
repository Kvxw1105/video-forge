import { lazy, Suspense, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Archive,
  ArrowCounterClockwise,
  ArrowRight,
  Clock,
  ClosedCaptioning,
  Export,
  FilmSlate,
  FolderOpen,
  Gear,
  Microphone,
  Moon,
  Plus,
  Sun,
  Trash,
} from '@phosphor-icons/react'
import { useTheme } from '../contexts/ThemeContext'
import { api } from '../lib/api'

const BrandScene = lazy(() => import('../components/visual/BrandScene'))

const WORKFLOW_STEPS = [
  { icon: Microphone, label: '文案配音', index: '01' },
  { icon: ClosedCaptioning, label: '字幕同步', index: '02' },
  { icon: FilmSlate, label: '素材编排', index: '03' },
  { icon: Export, label: '导出剪映', index: '04' },
]

function SectionHeading({ eyebrow, title, meta }: { eyebrow: string; title: string; meta?: string }) {
  return (
    <div className="section-heading">
      <div>
        <span className="section-index">{eyebrow}</span>
        <h2>{title}</h2>
      </div>
      {meta && <span className="section-meta">{meta}</span>}
    </div>
  )
}

export default function Home() {
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()
  const [projects, setProjects] = useState<any[]>([])
  const [templates, setTemplates] = useState<any[]>([])
  const [name, setName] = useState('')
  const [selectedTemplate, setSelectedTemplate] = useState('tpl_single_voiceover')
  const [creating, setCreating] = useState(false)
  const [deletedProjects, setDeletedProjects] = useState<any[]>([])
  const [showTrash, setShowTrash] = useState(false)
  const [operationError, setOperationError] = useState('')

  useEffect(() => {
    api.listProjects().then(setProjects).catch(console.error)
    api.listTemplates().then(setTemplates).catch(console.error)
    api.listDeletedProjects().then(setDeletedProjects).catch(console.error)
  }, [])

  const handleDelete = async (event: React.MouseEvent, projectId: string) => {
    event.stopPropagation()
    if (!confirm('确定把这个项目移入回收站？之后可以恢复。')) return
    try {
      setOperationError('')
      const result = await api.deleteProject(projectId)
      setProjects(previous => previous.filter(project => project.id !== projectId))
      if (result.trashItem) setDeletedProjects(previous => [result.trashItem, ...previous])
    } catch (error: any) {
      setOperationError(error?.message || '删除失败')
    }
  }

  const handleRestore = async (trashId: string) => {
    try {
      setOperationError('')
      const restored = await api.restoreProject(trashId)
      setDeletedProjects(previous => previous.filter(item => item.trashId !== trashId))
      setProjects(previous => [{ id: restored.id, name: restored.name, created_at: restored.created_at }, ...previous])
    } catch (error: any) {
      setOperationError(error?.message || '恢复失败')
    }
  }

  const handleCreate = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const project = await api.createProject(name.trim(), '9:16', selectedTemplate)
      navigate(`/editor/${project.id}`)
    } catch (error) {
      console.error(error)
      setOperationError('创建项目失败，请检查后端是否已启动')
    } finally {
      setCreating(false)
    }
  }

  return (
    <div className="home-shell">
      <Suspense fallback={null}>
        <BrandScene />
      </Suspense>

      <header className="home-topbar">
        <button className="home-brand" onClick={() => navigate('/')} aria-label="返回项目首页">
          <span className="home-brand-mark"><FilmSlate size={18} weight="fill" /></span>
          <span>
            <strong>VideoForge</strong>
            <small>视频草稿工台</small>
          </span>
        </button>

        <div className="home-topbar-meta" aria-hidden="true">
          <span>LOCAL EDITION</span>
          <span>PROJECTS {String(projects.length).padStart(2, '0')}</span>
        </div>

        <nav className="home-actions" aria-label="首页操作">
          <button className="icon-button" onClick={toggle} title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}>
            {theme === 'dark' ? <Sun size={16} weight="bold" /> : <Moon size={16} weight="bold" />}
          </button>
          <button className="btn-cinematic home-action-button" onClick={() => navigate('/library')}>
            <FolderOpen size={15} weight="bold" />
            <span>素材库</span>
          </button>
          <button className="btn-cinematic home-action-button" onClick={() => navigate('/settings/system')} title="运行环境检查">
            <Gear size={15} weight="bold" />
            <span>系统检查</span>
          </button>
          <button className="btn-cinematic home-action-button" onClick={() => setShowTrash(previous => !previous)}>
            <Archive size={15} weight="bold" />
            <span>回收站{deletedProjects.length > 0 ? ` ${deletedProjects.length}` : ''}</span>
          </button>
        </nav>
      </header>

      <main className="home-workspace">
        <motion.section
          initial={{ opacity: 0, x: -18 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
          className="home-manifesto"
        >
          <div>
            <p className="home-kicker">Material, then Expression</p>
            <h1 className="home-title">
              让素材
              <span>归位</span>
            </h1>
            <p className="home-lead">从声音开始组织画面，把零散素材锻造成可继续精修的视频草稿。</p>
          </div>

          <div className="workflow-rail">
            {WORKFLOW_STEPS.map(({ icon: Icon, label, index }) => (
              <div className="workflow-step" key={label}>
                <span>{index}</span>
                <Icon size={17} weight="duotone" />
                <strong>{label}</strong>
              </div>
            ))}
          </div>

          <div className="manifesto-note">
            <span>VF / 2026</span>
            <p>本地完成配音、字幕、素材编排与预览，再送入剪映完成最后一公里。</p>
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, delay: 0.08, ease: 'easeOut' }}
          className="glass-surface creation-panel"
        >
          <SectionHeading eyebrow="01 / CREATE" title="开始新项目" meta="默认竖屏 9:16" />

          <div className="creation-form">
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              onKeyDown={event => event.key === 'Enter' && handleCreate()}
              placeholder="输入项目名称"
              className="input-cinematic"
            />
            <button
              disabled={!name.trim() || creating}
              onClick={handleCreate}
              className="btn-gold creation-submit disabled:opacity-40"
            >
              <Plus size={17} weight="bold" />
              <span>{creating ? '创建中' : '创建项目'}</span>
              <ArrowRight size={15} weight="bold" />
            </button>
          </div>

          {operationError && <div className="operation-error">{operationError}</div>}

          <div className="template-heading">
            <span>选择结构模板</span>
            <small>先定结构，再进编辑器</small>
          </div>

          <div className="template-grid">
            {templates.map((template, index) => {
              const selected = selectedTemplate === template.id
              return (
                <button
                  key={template.id}
                  onClick={() => setSelectedTemplate(template.id)}
                  className={`template-card ${selected ? 'is-selected' : ''}`}
                >
                  <span className="template-number">{String(index + 1).padStart(2, '0')}</span>
                  <strong>{template.name}</strong>
                  <p>{template.description || '自定义项目结构'}</p>
                  <span className="template-ratio">{template.canvas?.ratio || '9:16'}</span>
                </button>
              )
            })}
          </div>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, x: 18 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.55, delay: 0.14, ease: 'easeOut' }}
          className="glass-surface projects-panel"
        >
          <SectionHeading
            eyebrow={showTrash ? '03 / ARCHIVE' : '02 / RECENT'}
            title={showTrash ? '回收站' : '最近项目'}
            meta={showTrash ? `${deletedProjects.length} 项` : `${projects.length} 项`}
          />

          {showTrash ? (
            <div className="project-list">
              {deletedProjects.length === 0 ? (
                <div className="empty-state"><Archive size={28} /><span>回收站为空</span></div>
              ) : deletedProjects.map(item => (
                <div key={item.trashId} className="project-row">
                  <span className="project-icon"><Archive size={15} /></span>
                  <strong>{item.name}</strong>
                  <button className="icon-button compact" onClick={() => handleRestore(item.trashId)} title="恢复项目">
                    <ArrowCounterClockwise size={14} weight="bold" />
                  </button>
                </div>
              ))}
            </div>
          ) : projects.length === 0 ? (
            <div className="empty-state"><FilmSlate size={30} /><span>还没有项目</span></div>
          ) : (
            <div className="project-list">
              {projects.map(project => (
                <div key={project.id} className="project-row" onClick={() => navigate(`/editor/${project.id}`)}>
                  <span className="project-icon"><Clock size={15} /></span>
                  <strong title={project.name}>{project.name}</strong>
                  <time>{project.created_at?.slice(0, 10)}</time>
                  <ArrowRight className="project-open" size={15} />
                  <button
                    className="project-delete"
                    onClick={event => handleDelete(event, project.id)}
                    title="移入回收站"
                  >
                    <Trash size={13} weight="bold" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </motion.section>
      </main>

      <footer className="home-footer">
        <span>VIDEO FORGE / LOCAL WORKSPACE</span>
        <span>VOICE · SUBTITLE · MATERIAL · DRAFT</span>
      </footer>
    </div>
  )
}

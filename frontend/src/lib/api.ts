const BASE = '/api'
export type JobStatus<T = any> = {
  jobId: string
  kind: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  progress: number
  phase: string
  message: string
  result: T | null
  error: string | null
}

async function request<T>(url: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
    ...opts,
  })
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: res.statusText }))
    const err: any = new Error(e.detail || e.msg || 'Request failed')
    err.status = res.status
    err.body = e
    throw err
  }
  return res.json()
}
export const api = {
  createProject: (name: string, canvasRatio = '9:16', templateId?: string) => request<any>('/projects', {
    method: 'POST',
    body: JSON.stringify({ name, canvas_ratio: canvasRatio, template_id: templateId }),
  }),
  getProject: (id: string) => request<any>(`/projects/${id}`),
  updateProject: (id: string, data: any) => request<any>(`/projects/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  listProjects: () => request<any[]>('/projects'),
  deleteProject: (id: string) => request<any>(`/projects/${id}`, { method: 'DELETE' }),
  listDeletedProjects: () => request<any[]>('/projects/trash/items'),
  restoreProject: (trashId: string) => request<any>(`/projects/trash/${encodeURIComponent(trashId)}/restore`, { method: 'POST' }),
  uploadAsset: async (projectId: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch(`${BASE}/projects/${projectId}/assets`, { method: 'POST', body: fd })
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || '上传失败') }
    return r.json()
  },
  generateVoiceover: (projectId: string, text: string, speed = 0, pitch = 0, engine = 'edge') =>
    request<any>(`/projects/${projectId}/voiceover`, { method: 'POST', body: JSON.stringify({ text, speed, pitch, engine }) }),
  exportJianying: async (projectId: string, cueMode = 'uniform') => {
    const r = await fetch(`${BASE}/projects/${projectId}/export/jianying?cue_mode=${encodeURIComponent(cueMode)}`, { method: 'POST' })
    if (!r.ok) {
      const e = await r.json().catch(() => ({ detail: r.statusText }))
      throw new Error(e.detail || e.msg || 'Export failed')
    }
    const blob = await r.blob()
    const cd = r.headers.get('content-disposition') || ''
    const match = cd.match(/filename\*=UTF-8''(.+?)(?:$|;)/) || cd.match(/filename="?(.+?)"?$/)
    const name = match ? decodeURIComponent(match[1]) : 'export_draft.zip'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = name; a.click()
    URL.revokeObjectURL(url)
  },
  /** 直接导出到剪映草稿目录 */
  exportJianyingDirect: async (projectId: string, cueMode = 'uniform') =>
    request<{ status: string; message: string; path: string; draft_name: string }>(
      `/projects/${projectId}/export/jianying-direct?cue_mode=${encodeURIComponent(cueMode)}`, { method: 'POST' }
    ),
  startExportJianyingDirectJob: async (projectId: string, cueMode = 'uniform') =>
    request<JobStatus<{ status: string; message: string; path: string; draft_name: string }>>(
      `/projects/${projectId}/export/jianying-direct/start?cue_mode=${encodeURIComponent(cueMode)}`, { method: 'POST' }
    ),
  getJob: <T = any>(jobId: string) => request<JobStatus<T>>(`/jobs/${jobId}`),
  /** 查询剪映草稿目录状态 */
  getJianyingStatus: () =>
    request<{ detected: boolean; path: string | null; drafts: { name: string; folder: string }[] }>(
      '/jianying-status'
    ),
  syncJianyingParams: (projectId: string) =>
    request<{ status: string; draftName: string; matchedBy: string; changes: { segments: number; subtitles: number }; project: any }>(
      `/projects/${projectId}/jianying/sync-params`, { method: 'POST', body: JSON.stringify({}) }
    ),
  /** 获取 TTS 设置 */
  getTtsSettings: () => request<any>('/settings/tts'),
  /** 更新 TTS 设置 */
  updateTtsSettings: (data: any) => request<any>('/settings/tts', { method: 'PUT', body: JSON.stringify(data) }),
  /** 测试 Fish Audio 接口 */
  testFishAudio: () => request<{ ok: boolean; message: string }>('/settings/tts/test/fish', { method: 'POST' }),
  /** 测试曼波 VIP 接口 */
  testManbo: () => request<{ ok: boolean; message: string }>('/settings/tts/test/manbo', { method: 'POST' }),
  /** 列出所有配音 */
  listVoiceovers: (projectId: string) => request<{ voiceovers: any[]; activeId: string | null }>(`/projects/${projectId}/voiceover/list`),
  /** 切换激活配音 */
  switchVoiceover: (projectId: string, voiceoverId: string) =>
    request<any>(`/projects/${projectId}/voiceover/switch`, { method: 'POST', body: JSON.stringify({ voiceoverId }) }),
  /** 删除配音 */
  deleteVoiceover: (projectId: string, voiceoverId: string) =>
    request<any>(`/projects/${projectId}/voiceover/delete`, { method: 'POST', body: JSON.stringify({ voiceoverId }) }),
  /** 获取配音音频 URL（供前端播放） */
  getVoiceoverUrl: (projectId: string, filePath?: string) => {
    if (filePath) {
      const name = filePath.replace(/\\/g, '/').split('/').pop() || filePath
      return `/api/projects/${projectId}/assets/project-file/${encodeURIComponent(name)}`
    }
    return ''
  },
  /** 生成视频预览 */
  generatePreview: (projectId: string, cueMode = 'uniform') =>
    request<{ status: string; previewUrl: string; duration: number }>(
      `/projects/${projectId}/preview?cue_mode=${encodeURIComponent(cueMode)}`, { method: 'POST' }
    ),
  startPreviewJob: (projectId: string, cueMode = 'uniform') =>
    request<JobStatus<{ status: string; previewUrl: string; duration: number }>>(
      `/projects/${projectId}/preview/start?cue_mode=${encodeURIComponent(cueMode)}`, { method: 'POST' }
    ),
  /** 模板 API */
  listTemplates: () => request<any[]>('/templates'),
  listTemplateProductionBatches: () => request<any[]>('/batches/template-production'),
  getTemplateProductionBatch: (batchId: string) => request<any>(`/batches/template-production/${encodeURIComponent(batchId)}`),
  startTemplateProductionBatch: (spec: any) => request<any>('/batches/template-production', { method: 'POST', body: JSON.stringify(spec) }),
  saveTemplate: (data: any) => request<any>('/templates', { method: 'POST', body: JSON.stringify(data) }),
  deleteTemplate: (id: string) => request<any>(`/templates/${id}`, { method: 'DELETE' }),
  /** SRT 导入 */
  importSrt: async (projectId: string, file: File) => {
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch(`${BASE}/projects/${projectId}/subtitles/import-srt`, { method: 'POST', body: fd })
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || '导入失败') }
    return r.json()
  },
  /** SRT 导出 */
  exportSrt: async (projectId: string) => {
    const r = await fetch(`${BASE}/projects/${projectId}/subtitles/export-srt`)
    if (!r.ok) {
      const e = await r.json().catch(() => ({ detail: r.statusText }))
      throw new Error(e.detail || '导出失败')
    }
    const blob = await r.blob()
    const cd = r.headers.get('content-disposition') || ''
    const match = cd.match(/filename\*=UTF-8''(.+?)(?:$|;)/) || cd.match(/filename="?(.+?)"?$/)
    const name = match ? decodeURIComponent(match[1]) : 'subtitles.srt'
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  },
  /** 素材库 API */
  listLibrary: () => request<any[]>('/library'),
  uploadToLibrary: async (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    const r = await fetch(`${BASE}/library`, { method: 'POST', body: fd })
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || '上传失败') }
    return r.json()
  },
  deleteLibraryAsset: (id: string) => request<any>(`/library/${id}`, { method: 'DELETE' }),
  importLibraryAsset: (assetId: string, projectId: string) =>
    request<any>(`/library/import/${assetId}/to/${projectId}`, { method: 'POST' }),
  importLibraryFolder: (folderName: string, projectId: string) =>
    request<any>(`/library/import-folder/${encodeURIComponent(folderName)}/to/${projectId}`, { method: 'POST' }),
  /** 音频分析 API */
  analyzeBgm: (projectId: string) =>
    request<{ status: string; analysis: any }>(`/projects/${projectId}/analyze-bgm`),
  getCuePoints: (projectId: string, mode: string, imageCount: number) =>
    request<{ status: string; bpm: number; duration: number; cue_points: any[]; analysis: any }>(
      `/projects/${projectId}/cue-points?mode=${mode}&image_count=${imageCount}`, { method: 'POST' }
    ),
  getStructuredAudioStatus: (projectId: string) => request<any>(`/projects/${projectId}/structured/audio/status`),
  generateFishAlignedAudio: (projectId: string, data: any) => request<any>(`/projects/${projectId}/structured/audio/fish-aligned`, { method: 'POST', body: JSON.stringify(data) }),
  previewStructuredVariant: (projectId: string, variantId: string) => request<any>(`/projects/${projectId}/structured/variants/${variantId}/preview`, { method: 'POST' }),
  exportStructuredVariantToJianYing: (projectId: string, variantId: string) => request<any>(`/projects/${projectId}/structured/variants/${variantId}/export/jianying-direct`, { method: 'POST', body: JSON.stringify({ policy: 'create_new' }) }),
  getVisualPlanContext: (projectId: string) => request<any>(`/projects/${projectId}/visual-plan/context`),
  getVisualPlan: (projectId: string) => request<any>(`/projects/${projectId}/visual-plan`),
  proposeVisualPlan: (projectId: string) => request<any>(`/projects/${projectId}/visual-plan/propose`, { method: 'POST', body: JSON.stringify({ mode: 'target_duration', targetDuration: 7 }) }),
  saveVisualPlan: (projectId: string, plan: any) => request<any>(`/projects/${projectId}/visual-plan`, { method: 'PUT', body: JSON.stringify({ plan }) }),
  exportVisualPack: (projectId: string) => request<any>(`/projects/${projectId}/visual-plan/generation-pack`, { method: 'POST' }),
  validateVisualPlan: (projectId: string) => request<any>(`/projects/${projectId}/visual-plan/validate`, { method: 'POST', body: JSON.stringify({}) }),
  renderCodeVisualOverlay: (projectId: string, sceneId: string, options: {
    rendererId: 'white_sketch' | 'silhouette' | 'pixel_rules' | 'mechanism_diagram'
    themeMode: 'dark' | 'light'
    overlayX: number
    overlayY: number
    overlayScale: number
    overlayDurationPolicy: 'loop' | 'freeze_last_frame' | 'trim'
    exportTransparentVideo?: boolean
  }) => request<any>(`/projects/${projectId}/visual-assets/code-visual/scenes/${encodeURIComponent(sceneId)}/regenerate`, {
    method: 'POST',
    body: JSON.stringify({
      sourceMode: 'visual_plan', exportPng: true, exportVideo: true, videoFps: 12,
      bindToProject: true, presentationMode: 'overlay', ...options,
    }),
  }),
  recommendCodeVisualOverlays: (projectId: string, sceneIds: string[] = []) => request<{ recommendations: any[] }>(`/projects/${projectId}/visual-assets/code-visual/recommend`, { method: 'POST', body: JSON.stringify({ sceneIds }) }),
  getStructuredCatalog: () => request<any[]>('/projects/structured/catalog'),
  parseStructuredMarkdown: (text: string) => request<any>('/structured/import/parse', { method: 'POST', body: JSON.stringify({ text, format: 'auto' }) }),
  createStructuredProject: (name: string, episode: any, ratio = '9:16') => request<any>('/projects/structured', { method: 'POST', body: JSON.stringify({ name, episode, canvas: { ratio } }) }),
  getStructuredEpisodeDraft: (projectId: string) => request<any>(`/projects/${projectId}/structured/draft`),
  updateStructuredEpisodeDraft: (projectId: string, data: any) => request<any>(`/projects/${projectId}/structured/draft`, { method: 'PATCH', body: JSON.stringify(data) }),
  compileComposition: (projectId: string) => request<any>(`/projects/${projectId}/composition/compile`, { method: 'POST' }),
  previewComposition: (projectId: string) => request<any>(`/projects/${projectId}/composition/preview`, { method: 'POST' }),
  exportCompositionToJianYing: (projectId: string) => request<any>(`/projects/${projectId}/composition/export/jianying-direct`, { method: 'POST', body: JSON.stringify({ policy: 'create_new' }) }),
  getFactoryItemVisuals: (batchId: string, itemId: string) => request<any>(`/agent-factory/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(itemId)}/visuals`),
  validateFactoryItemVisuals: (batchId: string, itemId: string) => request<any>(`/agent-factory/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(itemId)}/visuals/validate`, { method: 'POST', body: JSON.stringify({}) }),
  resumeFactoryItem: (batchId: string, itemId: string) => request<any>(`/agent-factory/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(itemId)}/resume`, { method: 'POST', body: JSON.stringify({}) }),
  uploadFactorySceneVisual: async (batchId: string, itemId: string, sceneId: string, file: File, replace = false) => {
    const form = new FormData(); form.append('sceneId', sceneId); form.append('replace', String(replace)); form.append('file', file)
    const response = await fetch(`${BASE}/agent-factory/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(itemId)}/visuals/upload`, { method: 'POST', body: form })
    if (!response.ok) { const body = await response.json().catch(() => ({})); const error: any = new Error(body?.detail?.message || body?.detail || '上传失败'); error.body = body; throw error }
    return response.json()
  },
  unbindFactorySceneVisual: (batchId: string, itemId: string, sceneId: string, deleteProjectAsset = false) => request<any>(`/agent-factory/batches/${encodeURIComponent(batchId)}/items/${encodeURIComponent(itemId)}/visuals/unbind`, { method: 'POST', body: JSON.stringify({ sceneId, deleteProjectAsset }) }),
  getVersion: () => request<any>('/version'),
  getAgentProviderSettings: () => request<any>('/settings/agent'),
  saveAgentProviderSettings: (data: any) => request<any>('/settings/agent', { method: 'PUT', body: JSON.stringify(data) }),
  testAgentProvider: (data: any) => request<any>('/settings/agent/test', { method: 'POST', body: JSON.stringify(data) }),
  fetchAgentProviderModels: (data: any) => request<any>('/settings/agent/models', { method: 'POST', body: JSON.stringify(data) }),
  uploadDirectorSrtIntake: async (file: File) => {
    const fd = new FormData(); fd.append('file', file)
    const response = await fetch(`${BASE}/director/intake/srt`, { method: 'POST', body: fd })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new Error(body?.detail?.message || body?.detail || body?.message || 'SRT import failed')
    }
    return response.json()
  },
  createDirectorRun: (data: any) => request<any>('/director/runs', { method: 'POST', body: JSON.stringify(data) }),
  listDirectorRuns: () => request<any[]>('/director/runs'),
  getDirectorRun: (runId: string) => request<any>('/director/runs/' + encodeURIComponent(runId)),
  getDirectorRunEvents: (runId: string, after = 0) => request<any>('/director/runs/' + encodeURIComponent(runId) + '/events?after=' + after),
  approveDirectorRun: (runId: string, approvalId: string, decision = 'replace') => request<any>('/director/runs/' + encodeURIComponent(runId) + '/approvals', { method: 'POST', body: JSON.stringify({ approvalId, decision }) }),
}

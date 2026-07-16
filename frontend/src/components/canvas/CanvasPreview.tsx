import { useRef, useEffect, useMemo, useState, useCallback } from 'react'
import {
  calcSubtitleBox,
  overlayToCanvasPixels,
  overlayToFFmpegExprs,
  scaleFontSize,
  normalizeHex,
} from '../../lib/renderParams'

function getAssetUrl(projectId: string, assetPath: string | null): string | null {
  if (!assetPath) return null
  const normalized = assetPath.replace(/\\/g, '/')
  const parts = normalized.split('/')
  const filename = parts[parts.length - 1]
  if (parts.includes('_library') || filename.startsWith('lib_')) {
    return `/api/library/raw/${encodeURIComponent(filename)}`
  }
  if (parts.includes('assets')) {
    return `/api/projects/${projectId}/assets/raw/assets/${encodeURIComponent(filename)}`
  }
  return `/api/projects/${projectId}/assets/project-file/${encodeURIComponent(filename)}`
}

type DragTarget = 'image' | 'title' | 'watermark' | null

export default function CanvasPreview({
  projectId, imagePath, scale, fit, positionX = 0.5, positionY = 0.5, canvasW, canvasH, bgColor = '#000000', subtitles, subtitleFontSize = 48, subtitleEnabled = true,
  subtitlePosition = 'bottom_center',
  segmentType, materialCount = 0, shuffleMode = true, onPositionChange,
  totalDuration = 0,
  voiceoverStartAt = 0,
  voiceoverDuration = 0,
  voiceoverUrl,
  title = { text: '', enabled: false, fontSize: 48, opacity: 1, x: 0.5, y: 0.08, color: '#ffffff' },
  watermark = { text: '', enabled: false, fontSize: 24, opacity: 0.35, x: 0.85, y: 0.92, color: '#ffffff' },
  directoryProgress = {},
  brightness = 0,
  contrast = 1,
  onTitlePositionChange,
  onWatermarkPositionChange,
}: {
  projectId: string
  imagePath: string | null
  scale: number
  fit: string
  positionX?: number
  positionY?: number
  canvasW: number
  canvasH: number
  bgColor?: string
  subtitles: any[]
  subtitleFontSize?: number
  subtitleEnabled?: boolean
  subtitlePosition?: string
  segmentType?: string
  materialCount?: number
  shuffleMode?: boolean
  onPositionChange?: (x: number, y: number) => void
  totalDuration?: number
  voiceoverStartAt?: number
  voiceoverDuration?: number
  voiceoverUrl?: string | null
  title?: any
  watermark?: any
  directoryProgress?: any
  brightness?: number
  contrast?: number
  onTitlePositionChange?: (x: number, y: number) => void
  onWatermarkPositionChange?: (x: number, y: number) => void
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const [containerSize, setContainerSize] = useState({ w: 0, h: 0 })
  const [videoFrameReady, setVideoFrameReady] = useState(false)
  const [redrawTick, setRedrawTick] = useState(0) // force canvas redraw on bgColor/scale/fit change

  // Drag state — supports image, title, watermark
  const dragRef = useRef<{
    target: DragTarget
    startX: number; startY: number
    startPosX: number; startPosY: number
  } | null>(null)
  const [dragTarget, setDragTarget] = useState<DragTarget>(null)

  // Internal positions (0-1 range on canvas)
  const imgPosRef = useRef({ x: positionX, y: positionY })
  const titlePosRef = useRef({ x: title.x ?? 0.5, y: title.y ?? 0.08 })
  const watermarkPosRef = useRef({ x: watermark.x ?? 0.85, y: watermark.y ?? 0.92 })

  // Sync ref from props
  useEffect(() => { titlePosRef.current = { x: title.x ?? 0.5, y: title.y ?? 0.08 } }, [title.x, title.y])
  useEffect(() => { watermarkPosRef.current = { x: watermark.x ?? 0.85, y: watermark.y ?? 0.92 } }, [watermark.x, watermark.y])
  useEffect(() => {
    imgPosRef.current = { x: positionX, y: positionY }
    setRedrawTick(t => t + 1)
  }, [imagePath, positionX, positionY])

  // Force canvas redraw when visual props change
  useEffect(() => { setRedrawTick(t => t + 1) }, [bgColor, scale, fit])

  // Playback state
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const rafRef = useRef<number | null>(null)
  const lastFrameRef = useRef<number>(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const url = getAssetUrl(projectId, imagePath)
  const visibleSubtitles = subtitleEnabled ? subtitles : []

  const duration = useMemo(() => {
    if (totalDuration > 0) return totalDuration
    if (visibleSubtitles.length > 0) return Math.max(...visibleSubtitles.map((s: any) => s.end || 0))
    return 5
  }, [totalDuration, visibleSubtitles])

  // Audio setup
  useEffect(() => {
    if (voiceoverUrl) {
      const audio = new Audio(voiceoverUrl)
      audio.preload = 'auto'
      audioRef.current = audio
      return () => { audio.pause(); audioRef.current = null }
    }
  }, [voiceoverUrl])

  // Playback loop
  useEffect(() => {
    if (!playing) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      return
    }
    lastFrameRef.current = performance.now()
    const tick = (now: number) => {
      const delta = (now - lastFrameRef.current) / 1000
      lastFrameRef.current = now
      setCurrentTime(prev => {
        const next = prev + delta
        if (next >= duration) {
          setPlaying(false)
          if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0 }
          return 0
        }
        return next
      })
      rafRef.current = requestAnimationFrame(tick)
    }
    rafRef.current = requestAnimationFrame(tick)
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current) }
  }, [playing, duration])

  const togglePlay = useCallback(() => {
    setPlaying(prev => {
      const next = !prev
      if (next && audioRef.current) {
        audioRef.current.currentTime = currentTime
        audioRef.current.play().catch(() => {})
      } else if (!next && audioRef.current) {
        audioRef.current.pause()
      }
      return next
    })
  }, [currentTime])

  const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const t = parseFloat(e.target.value)
    setCurrentTime(t)
    if (audioRef.current) audioRef.current.currentTime = t
  }, [])

  // Active subtitle
  const activeSub = useMemo(() => {
    if (!visibleSubtitles.length) return null
    return visibleSubtitles.find((s: any) => currentTime >= s.start && currentTime < s.end) || null
  }, [visibleSubtitles, currentTime])

  // Container resize
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0].contentRect
      setContainerSize({ w: cr.width, h: cr.height })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const display = useMemo(() => {
    if (containerSize.w === 0 || containerSize.h === 0) return { w: 0, h: 0 }
    const canvasRatio = canvasW / canvasH
    const containerRatio = containerSize.w / containerSize.h
    let w: number, h: number
    if (containerRatio > canvasRatio) {
      h = containerSize.h - 32
      w = h * canvasRatio
    } else {
      w = containerSize.w - 32
      h = w / canvasRatio
    }
    return { w: Math.round(w), h: Math.round(h) }
  }, [containerSize, canvasW, canvasH])

  // Drag handlers — unified for image/title/watermark
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return
    const mx = (e.clientX - rect.left) / rect.width
    const my = (e.clientY - rect.top) / rect.height

    // Determine what was clicked: title > watermark > image
    let target: DragTarget = null
    if (title.enabled && title.text && Math.abs(mx - (titlePosRef.current.x)) < 0.25 && Math.abs(my - (titlePosRef.current.y)) < 0.1) {
      target = 'title'
    } else if (watermark.enabled && watermark.text && Math.abs(mx - (watermarkPosRef.current.x)) < 0.25 && Math.abs(my - (watermarkPosRef.current.y)) < 0.1) {
      target = 'watermark'
    } else if (onPositionChange) {
      target = 'image'
    }

    if (!target) return
    setDragTarget(target)

    const startPos = target === 'title' ? titlePosRef.current :
                     target === 'watermark' ? watermarkPosRef.current :
                     imgPosRef.current

    dragRef.current = { target, startX: e.clientX, startY: e.clientY, startPosX: startPos.x, startPosY: startPos.y }
    e.preventDefault()
  }, [title, watermark, onPositionChange])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current || !canvasRef.current) return
    const rect = canvasRef.current.getBoundingClientRect()
    const dx = (e.clientX - dragRef.current.startX) / rect.width
    const dy = (e.clientY - dragRef.current.startY) / rect.height
    const newX = Math.max(0, Math.min(1, dragRef.current.startPosX + dx))
    const newY = Math.max(0, Math.min(1, dragRef.current.startPosY + dy))
    const { target } = dragRef.current

    if (target === 'title') {
      titlePosRef.current = { x: newX, y: newY }
      onTitlePositionChange?.(newX, newY)
    } else if (target === 'watermark') {
      watermarkPosRef.current = { x: newX, y: newY }
      onWatermarkPositionChange?.(newX, newY)
    } else if (target === 'image') {
      imgPosRef.current = { x: newX, y: newY }
      onPositionChange?.(newX, newY)
    }
    setRedrawTick(t => t + 1)  // Force canvas redraw during drag
  }, [onPositionChange, onTitlePositionChange, onWatermarkPositionChange])

  const handleMouseUp = useCallback(() => { dragRef.current = null; setDragTarget(null) }, [])

  // Video first frame extraction
  useEffect(() => {
    if (segmentType !== 'video' || !url) { setVideoFrameReady(false); return }
    setVideoFrameReady(false)
    const video = document.createElement('video')
    video.crossOrigin = 'anonymous'
    video.preload = 'auto'
    video.muted = true
    video.src = url
    video.onloadeddata = () => {
      video.currentTime = 0.1
    }
    video.onseeked = () => {
      videoRef.current = video
      setVideoFrameReady(true)
    }
    video.onerror = () => { setVideoFrameReady(false) }
  }, [segmentType, url])

  // Canvas render
  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx || display.w === 0) return

    const dpr = window.devicePixelRatio || 1
    canvas.width = Math.max(1, Math.floor(display.w * dpr))
    canvas.height = Math.max(1, Math.floor(display.h * dpr))
    canvas.style.width = `${display.w}px`
    canvas.style.height = `${display.h}px`
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, display.w, display.h)

    // Background
    ctx.fillStyle = bgColor
    ctx.fillRect(0, 0, display.w, display.h)

    // Draw image or video frame
    const drawMedia = (imgSource: CanvasImageSource, imgW: number, imgH: number) => {
      const imgRatio = imgW / imgH
      const canvasRatio = display.w / display.h
      let dw = display.w, dh = display.h, dx = 0, dy = 0
      const s = scale
      if (fit === 'contain') {
        if (imgRatio > canvasRatio) { dw = display.w * s; dh = dw / imgRatio }
        else { dh = display.h * s; dw = dh * imgRatio }
      } else if (fit === 'cover') {
        if (imgRatio > canvasRatio) { dh = display.h * s; dw = dh * imgRatio }
        else { dw = display.w * s; dh = dw / imgRatio }
      } else {
        dw = display.w * s; dh = display.h * s
      }
      dx = (display.w - dw) / 2; dy = (display.h - dh) / 2
      const posOffX = (imgPosRef.current.x - 0.5) * display.w
      const posOffY = (imgPosRef.current.y - 0.5) * display.h
      ctx.drawImage(imgSource, dx + posOffX, dy + posOffY, dw, dh)
    }

    // Draw title text on canvas
    const drawTitleText = () => {
      if (!title.enabled || !title.text) return
      const { x: tx, y: ty } = overlayToCanvasPixels(title, display.w, display.h)
      const fs = scaleFontSize(title.fontSize || 48, display.w, canvasW)
      ctx.save()
      ctx.globalAlpha = title.opacity ?? 1
      ctx.font = `bold ${fs}px "Geist", "PingFang SC", "Microsoft YaHei", sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      // Text shadow
      ctx.shadowColor = 'rgba(0,0,0,0.6)'
      ctx.shadowBlur = 4
      ctx.fillStyle = title.color || '#ffffff'
      ctx.fillText(title.text, tx, ty)
      ctx.restore()
    }

    // Draw watermark text on canvas
    const drawWatermarkText = () => {
      if (!watermark.enabled || !watermark.text) return
      const { x: wx, y: wy } = overlayToCanvasPixels(watermark, display.w, display.h)
      const fs = scaleFontSize(watermark.fontSize || 24, display.w, canvasW)
      ctx.save()
      ctx.globalAlpha = watermark.opacity ?? 0.35
      ctx.font = `${fs}px "Geist", "PingFang SC", "Microsoft YaHei", sans-serif`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      ctx.fillStyle = watermark.color || '#ffffff'
      ctx.fillText(watermark.text, wx, wy)
      ctx.restore()
    }

    // Draw directory progress text (voiceover section only)
    const drawDirectoryProgress = () => {
      if (!directoryProgress.enabled || !directoryProgress.text) return
      const start = Math.max(0, Number(voiceoverStartAt || 0))
      const dur = Math.max(0, Number(voiceoverDuration || 0))
      if (dur <= 0 || currentTime < start || currentTime > start + dur) return
      const p = Math.max(0, Math.min(1, (currentTime - start) / dur))
      const sx = Number(directoryProgress.startX ?? -0.35)
      const ex = Number(directoryProgress.endX ?? 1.05)
      const x = (sx + (ex - sx) * p) * display.w
      const y = Number(directoryProgress.y ?? 0.94) * display.h
      const fs = scaleFontSize(Number(directoryProgress.fontSize || 22), display.w, canvasW)
      ctx.save()
      ctx.globalAlpha = Number(directoryProgress.opacity ?? 0.72)
      ctx.font = `${fs}px "Geist", "PingFang SC", "Microsoft YaHei", sans-serif`
      ctx.textAlign = 'left'
      ctx.textBaseline = 'middle'
      ctx.shadowColor = 'rgba(0,0,0,0.55)'
      ctx.shadowBlur = 3
      ctx.fillStyle = directoryProgress.color || '#F4EBDD'
      ctx.fillText(directoryProgress.text, x, y)
      ctx.restore()
    }

    // Draw active subtitle
    const drawActiveSubtitle = () => {
      if (!activeSub?.text) return
      drawSubtitle(ctx, activeSub.text, display, subtitleFontSize, canvasW, subtitlePosition)
    }

    // Apply brightness/contrast filter for media
    const adjFilter = (brightness !== 0 || contrast !== 1)
      ? `brightness(${1 + brightness}) contrast(${contrast})`
      : 'none'

    // If video first frame is ready, use it
    if (segmentType === 'video' && videoFrameReady && videoRef.current) {
      ctx.filter = adjFilter
      drawMedia(videoRef.current, videoRef.current.videoWidth, videoRef.current.videoHeight)
      ctx.filter = 'none'  // Reset for overlay text
      drawTitleText()
      drawWatermarkText()
      drawDirectoryProgress()
      drawActiveSubtitle()
      return
    }

    // If image URL exists, load and draw
    if (url && segmentType !== 'video') {
      const img = new Image()
      img.onload = () => {
        ctx.clearRect(0, 0, display.w, display.h)
        ctx.fillStyle = bgColor
        ctx.fillRect(0, 0, display.w, display.h)
        ctx.filter = adjFilter
        drawMedia(img, img.width, img.height)
        ctx.filter = 'none'  // Reset for overlay text
        drawTitleText()
        drawWatermarkText()
        drawActiveSubtitle()
      }
      img.onerror = () => {
        ctx.fillStyle = '#71717a'
        ctx.font = '14px Geist, sans-serif'
        ctx.textAlign = 'center'
        ctx.fillText('图片加载失败', display.w / 2, display.h / 2)
      }
      img.src = url
    } else if (segmentType === 'video' && !videoFrameReady) {
      // Video loading placeholder
      ctx.fillStyle = '#1a1a1a'
      ctx.fillRect(0, 0, display.w, display.h)
      ctx.fillStyle = '#52525b'
      ctx.font = '14px Geist, sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText('视频首帧加载中...', display.w / 2, display.h / 2)
      drawTitleText()
      drawWatermarkText()
      drawDirectoryProgress()
      drawActiveSubtitle()
    } else {
      // No media
      drawTitleText()
      drawWatermarkText()
      drawDirectoryProgress()
      drawActiveSubtitle()
    }
  }, [url, scale, fit, display, activeSub, subtitleFontSize, subtitlePosition, canvasW, canvasH, bgColor,
      title, watermark, directoryProgress, currentTime, voiceoverStartAt, voiceoverDuration,
      titlePosRef.current.x, titlePosRef.current.y,
      watermarkPosRef.current.x, watermarkPosRef.current.y,
      videoFrameReady, segmentType, redrawTick, brightness, contrast, positionX, positionY])

  const hasMultipleMaterials = materialCount > 1

  // Cursor style based on drag target
  const cursorStyle = dragTarget === 'image' ? 'grabbing' :
    dragTarget === 'title' || dragTarget === 'watermark' ? 'grabbing' :
    (title.enabled && title.text) || (watermark.enabled && watermark.text) || onPositionChange ? 'default' : 'default'

  return (
    <div ref={wrapRef} className="flex-1 w-full h-full flex flex-col items-center justify-center p-4 sm:p-8 overflow-hidden relative" style={{ background: 'var(--bg-base)' }}>
      {/* Material count badge */}
      {hasMultipleMaterials && (
        <div className="absolute top-4 left-4 z-10 status-pill px-2.5 py-1 text-[11px]" data-tone="ok">
          {materialCount} 段素材 · {shuffleMode ? '随机' : '顺序'}
        </div>
      )}

      {/* Playback time badge */}
      {visibleSubtitles.length > 0 && (
        <div className="absolute top-4 right-4 z-10 status-pill px-2.5 py-1 text-[11px] font-mono" data-tone="ok">
          {currentTime.toFixed(1)}s / {duration.toFixed(1)}s
        </div>
      )}

      {/* Canvas — always rendered, handles both image and video */}
      <canvas
        ref={canvasRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        className="rounded-lg shadow-lg border"
        style={{
          display: display.w ? 'block' : 'none',
          position: 'relative',
          cursor: cursorStyle,
          borderColor: 'var(--border)',
        }}
      />

      {/* Playback controls */}
      {visibleSubtitles.length > 0 && (
        <div className="flex items-center gap-3 mt-3 w-full max-w-md">
          <button
            onClick={togglePlay}
            className="w-8 h-8 rounded-full flex items-center justify-center transition-colors flex-shrink-0"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)' }}
          >
            {playing ? (
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="4" width="4" height="16" rx="1" />
                <rect x="14" y="4" width="4" height="16" rx="1" />
              </svg>
            ) : (
              <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M8 5v14l11-7z" />
              </svg>
            )}
          </button>
          <input
            type="range"
            name="previewSeek"
            aria-label="预览进度"
            min={0}
            max={duration}
            step={0.05}
            value={currentTime}
            onChange={handleSeek}
            className="flex-1 h-1.5 cursor-pointer"
            style={{ accentColor: 'var(--accent)' }}
          />
          <span className="text-[11px] font-mono w-16 text-right flex-shrink-0" style={{ color: 'var(--text-muted)' }}>
            {currentTime.toFixed(1)}s
          </span>
        </div>
      )}

      {/* Drag hint */}
      {(title.enabled && title.text) && (
        <div className="absolute bottom-14 left-1/2 -translate-x-1/2 text-[10px] italic pointer-events-none" style={{ color: 'var(--text-muted)' }}>
          拖拽标题/水印/素材移动位置
        </div>
      )}
    </div>
  )
}

function drawSubtitle(
  ctx: CanvasRenderingContext2D,
  text: string,
  display: { w: number; h: number },
  subtitleFontSize: number,
  canvasW: number,
  subtitlePosition: string,
) {
  const fontSize = scaleFontSize(subtitleFontSize, display.w, canvasW)
  ctx.font = `bold ${fontSize}px "Geist", "PingFang SC", "Microsoft YaHei", sans-serif`

  const maxWidth = display.w * 0.85
  const metrics = ctx.measureText(text)
  let displayText = text
  if (metrics.width > maxWidth) {
    displayText = text.slice(0, Math.floor(text.length * maxWidth / metrics.width)) + '…'
  }

  const tw = Math.min(ctx.measureText(displayText).width + 24, maxWidth + 24)
  const th = fontSize + 16

  const pos = subtitlePosition || 'bottom_center'
  const { x: bx, y: by, textX, textAlign } = calcSubtitleBox(pos, display.w, display.h, tw, th)
  const textY = by + th / 2 + fontSize * 0.35

  ctx.textAlign = textAlign
  ctx.textBaseline = 'middle'

  // Background pill
  ctx.fillStyle = 'rgba(20,20,18,0.72)'
  roundRect(ctx, bx, by, tw, th, 8)
  ctx.fill()

  // Text with shadow
  ctx.fillStyle = 'rgba(245,242,235,1)'
  ctx.shadowColor = 'rgba(0,0,0,0.6)'
  ctx.shadowBlur = 3
  ctx.fillText(displayText, textX, textY)
  ctx.shadowBlur = 0
}

function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  const radius = Math.min(r, w / 2, h / 2)
  ctx.beginPath()
  ctx.moveTo(x + radius, y)
  ctx.lineTo(x + w - radius, y)
  ctx.quadraticCurveTo(x + w, y, x + w, y + radius)
  ctx.lineTo(x + w, y + h - radius)
  ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h)
  ctx.lineTo(x + radius, y + h)
  ctx.quadraticCurveTo(x, y + h, x, y + h - radius)
  ctx.lineTo(x, y + radius)
  ctx.quadraticCurveTo(x, y, x + radius, y)
  ctx.closePath()
}

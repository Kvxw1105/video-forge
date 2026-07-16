/**
 * Shared rendering parameters for CanvasPreview, FFmpeg renderer, and JianYing draft.
 * All coordinate/size/color conversions live here so the three renderers stay in sync.
 */

export type Position3x3 = `${'top' | 'middle' | 'bottom'}_${'left' | 'center' | 'right'}`

export interface SubtitleStyle {
  fontSize?: number
  position?: Position3x3 | string
  color?: string
  opacity?: number
}

export interface OverlayItem {
  text?: string
  enabled?: boolean
  fontSize?: number
  opacity?: number
  x?: number
  y?: number
  color?: string
}

/**
 * Convert a 3x3 subtitle position preset to normalized anchor point (0..1).
 */
export function getSubtitleAnchor(position?: string): { x: number; y: number } {
  if (!position) position = 'bottom_center'
  const [vert, horiz] = position.split('_') as [string, string]
  return {
    x: horiz === 'left' ? 0 : horiz === 'right' ? 1 : 0.5,
    y: vert === 'top' ? 0 : vert === 'middle' ? 0.5 : 1,
  }
}

/**
 * Compute subtitle box position for CanvasPreview.
 */
export function calcSubtitleBox(
  position: string,
  displayW: number,
  displayH: number,
  boxW: number,
  boxH: number,
  marginRatio = 0.05
): { x: number; y: number; textX: number; textAlign: CanvasTextAlign } {
  const [vert, horiz] = (position || 'bottom_center').split('_') as [string, string]
  const margin = displayW * marginRatio

  let y = displayH - boxH - margin
  if (vert === 'top') y = margin
  else if (vert === 'middle') y = (displayH - boxH) / 2

  let x = (displayW - boxW) / 2
  let textX = displayW / 2
  let textAlign: CanvasTextAlign = 'center'

  if (horiz === 'left') {
    x = margin
    textX = x + boxW / 2
  } else if (horiz === 'right') {
    x = displayW - boxW - margin
    textX = x + boxW / 2
  }

  return { x, y, textX, textAlign }
}

/**
 * Scale a canvas pixel fontSize down to the displayed canvas size.
 * CanvasPreview draws at display.w x display.h but the project canvas is canvasW x canvasH.
 */
export function scaleFontSize(fontSize: number, displayW: number, canvasW: number): number {
  return Math.max(1, Math.round((fontSize * displayW) / canvasW))
}

/**
 * Convert overlay normalized position (0..1) to Canvas pixel coordinates.
 */
export function overlayToCanvasPixels(item: OverlayItem, displayW: number, displayH: number): { x: number; y: number } {
  return {
    x: (item.x ?? 0.5) * displayW,
    y: (item.y ?? 0.08) * displayH,
  }
}

/**
 * Convert overlay normalized position to FFmpeg drawtext x/y expressions.
 * x,y are center-anchor in our model.
 */
export function overlayToFFmpegExprs(item: OverlayItem, w: number, h: number): { x: string; y: string } {
  const x = item.x ?? 0.5
  const y = item.y ?? 0.08
  return {
    x: `w*${x}-text_w/2`,
    y: `h*${y}-text_h/2`,
  }
}

/**
 * Convert overlay normalized position to JianYing transform coordinates.
 * JianYing: (0,0)=center, ±1=edge.
 */
export function overlayToJianYingTransform(item: OverlayItem): { tx: number; ty: number } {
  return {
    tx: ((item.x ?? 0.5) - 0.5) * 2,
    ty: ((item.y ?? 0.5) - 0.5) * 2,
  }
}

/**
 * Convert canvas pixel fontSize to JianYing TextStyle.size.
 * Empirical ratio: 1 JY unit ≈ 3 canvas pixels for 1080p-class output.
 */
export function fontSizeToJianYing(fontSize: number): number {
  return Math.max(2, fontSize / 3.0)
}

/**
 * Parse hex color string (e.g. #ffffff or #fff) to 6-digit hex.
 */
export function normalizeHex(color?: string): string {
  if (!color) return 'ffffff'
  let c = color.trim().replace('#', '')
  if (c.length === 3) {
    c = c.split('').map(ch => ch + ch).join('')
  }
  return c.slice(0, 6) || 'ffffff'
}

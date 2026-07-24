import assert from 'node:assert/strict'
import test from 'node:test'

import { formatBytes, formatDuration, mediaStreamUrl, requireSucceeded } from './mediaProcessing.ts'

test('formats media facts for the compact asset inspector', () => {
  assert.equal(formatDuration(65.25), '1:05.3')
  assert.equal(formatDuration(undefined), '--')
  assert.equal(formatBytes(2 * 1024 * 1024), '2.0 MB')
})

test('turns structured provider failures into user-facing errors', () => {
  assert.throws(
    () => requireSucceeded({
      execution: {
        id: 'run-1',
        status: 'failed',
        capability: 'audio.extract',
        providerError: { message: '源视频没有音轨' },
      },
      recordPath: 'runs/run-1.json',
    }),
    /源视频没有音轨/,
  )
})

test('encodes project and Chinese media paths', () => {
  assert.equal(
    mediaStreamUrl('project a', 'assets/中文 视频.mp4'),
    '/api/projects/project%20a/assets/stream?path=assets%2F%E4%B8%AD%E6%96%87%20%E8%A7%86%E9%A2%91.mp4',
  )
})

# VideoForge — Project Memory

> **Read this first** before working on UI, design, or "make it look better" tasks.
> These are hard-won lessons from real user feedback. Violating them means rework.

---

## 1. Design Philosophy: Progressive Contrast, NOT Inversion

**User's rule (verbatim):**
> "如果想要实现这种方式，也可以换一种，比如使用按钮组件，做出深度或者弹簧的感觉，写了之后，它会有按进去或者发光的效果。但是没必要这样：只要只按了这一个东西，它的字变白，其他的字就是黑的。"

**Do NOT** do "selected = white-on-gold; unselected = white-on-dark" pattern.
That makes the entire button group flip to "white text" once one is selected, which kills readability of unselected siblings.

### Button states (CORRECT pattern)

| State | Background | Text | Border | Visual |
|---|---|---|---|---|
| **Unselected** | `var(--bg-surface)` (close to bg-base) | `var(--text-primary)` (dark in light mode, light in dark) | thin `--border` | Sinks into background |
| **Hover** | `var(--bg-elevated)` (one shade deeper) | same dark | `--border-accent` | Depth without inversion |
| **Active/Pressed** | bg-elevated + `transform: scale(0.97)` | — | — | Physical press feel |
| **Selected** | `var(--bg-accent)` (gold) | white | `box-shadow: 0 0 0 2px var(--accent-bg)` ring | Pops with glow ring |

The progression is **background depth**, not **text color flip**.

---

## 2. Light Mode Gotchas

### 2.1 `bg-elevated` is NOT a "dark block" in light mode

In dark mode, `bg-elevated = rgba(51,46,40,0.6)` (deep brown, light text works).

In light mode, `bg-elevated` should be a **mid-light gray** (e.g. `#e8dfd0`), used **only for hover/active depth** — NOT as a base button background.

**WRONG:** `bg-elevated + text-inverse` for unselected button in light mode
→ Looks like a dark block stuck on a light page; user reads it as "this is special" / "something's wrong"

**RIGHT:** `bg-surface + text-primary` for unselected, `bg-elevated` only on hover/active
→ Button visually integrates with the page, only the selected one jumps out

### 2.2 Anti-pattern: don't use `[style*="--bg-elevated"]` attribute selector hack

Tempting to globally flip "any bg-elevated element gets white text in light mode" — DON'T. This hard-codes the wrong design assumption (that all "elevated" elements want inverted text) into CSS, and breaks as soon as someone uses bg-elevated for a non-inverted context (e.g. hover depth).

Instead: fix the **specific components** that have wrong text colors.

### 2.3 Contrast rules to memorize

| Element | Light mode | Dark mode |
|---|---|---|
| Button unselected | bg-surface (light) + text-primary (dark) | bg-elevated (dark) + text-primary (light) |
| Button selected | bg-accent (gold) + text-inverse (white) | same |
| Input field | bg-surface (light) + text-primary (dark) | bg-elevated (dark) + text-primary (light) |
| Card / panel | bg-surface + text-primary | bg-elevated + text-primary (text-primary is already light in dark) |
| Disabled / placeholder | text-muted | text-muted |

`text-muted` in light mode must be **deep enough** to hit AA 4.5:1. Old `#8b7e6f` on `#f5f0e8` only gave 3.4:1 — fixed to `#7a6e5a` (4.7:1).

---

## 3. User's color philosophy (cinematic, low-saturation)

User wants **cinematic / mid-century / low-saturation** aesthetic, NOT "AI purple/blue glow" cliché. Specifically called out:

- Warm brown / parchment backgrounds (not pure black `#000`, use `#1a1814` off-black)
- Cormorant Garamond serif for headings, Crimson Pro for body
- Gold accent (`#b8956a` dark / `#8b7355` light), NOT neon
- Grain + vignette overlay (subtle, 0.02-0.035 opacity)
- Banned: `box-shadow` glows, gradient text, oversized H1, Inter font

---

## 4. When user pushes back, the user is usually right

Pattern observed multiple times:
- User said "灰底配白字" was wrong → I had used a global CSS hack to force this pattern → it broke 12 components
- User said "弹窗里不能上传/不能撤回" → I had only designed one-way flow
- User said "新建点不开" → I assumed data was lost; **backend was actually fine**, the problem was Windows process management

**Rule:** when user reports something is broken, check the **whole stack** (frontend → backend → process) before declaring "code bug". The actual cause is often environmental, not code.

---

## 5. Windows background process management

Background uvicorn processes get **killed by the sandbox when session goes idle**. Stable launch pattern:

```python
subprocess.Popen(
    [sys.executable, '-m', 'uvicorn', 'main:app', '--port', '8000'],
    stdin=subprocess.DEVNULL,
    stdout=open(r'C:\...\uv8000.log', 'w'),
    stderr=subprocess.STDOUT,
    creationflags=0x00000008,  # DETACHED_PROCESS
)
```

`run_in_background=true` (Bash tool) **is not enough** — process gets reaped when the shell context resets. Must use Python subprocess + DETACHED_PROCESS flag.

---

## 6. Editor / project UX invariants

- **`/editor/:id` page** must show **project_id + error + "重新加载" + "返回首页"** when project is missing, not just "项目不存在"
- **Library picker modal** must have:
  - Back button (when folder is selected) to return to folder list
  - "上传到素材库" entry inside the modal
  - X button to close
- **AssetThumb** in library must show: file extension, size (auto KB/MB), import date
- **CanvasPreview** when batch assets exist (>1): show grid + "生成轮播" button + clear button

---

## 7. Audio engine catalog (V0)

| Engine | Status | Notes |
|---|---|---|
| `edge` | ✅ default | Free, local |
| `manbo` (VIP) | ✅ | 250-299 char limit, intermittent 500s |
| `fish_audio` | ✅ | 232万 community voices. `s2.1-pro-free` is $0.00/MTok. Reference IDs: 风吟 754f...140 (纪录片), 曼波 b255...44f (教学) |
| `custom` | ✅ | User-defined endpoint |
| `none` | ✅ | No audio, subtitles only |

`Fish Audio` key env: 用户的 key 通过 `PUT /api/settings/tts` 写入 `tts_settings.json`，**不**入 git。

---

## 8. Audio analysis (BPM / beat / cue)

`engines/audio_analyzer.py` 用 librosa 跑（subprocess，避免污染主进程）：

- `bpm`: 整曲 BPM
- `beats`: 拍点时间戳（秒）
- `onsets`: 音头位置（更密）
- `energy`: 时间-能量曲线
- `pitch`: 时间-音高
- `sections`: 段落分割（基于能量）

4 种卡点模式：beat / onset / energy / uniform。所有模式都返回指定数量的 cue points（用 `_ensure_count()` 保证）。

---

## 9. Renderer invariants (engines/renderer.py)

- 时长 = `max(配音, 字幕, 片段, 5s) + 缓冲`
- 多片段不足时**循环**（不是黑屏）
- 音频比视频短时用 `apad` 补静音
- `drawtext` 用 `,` 拼接（不是 `:`），`between(t,...)` 中逗号不转义
- 字幕字号 / 位置 / 颜色 / 描边在剪映草稿中写 `TextSegment.clip_settings`

---

## 10. Vite proxy / dev server

- `vite.config.ts` 的 proxy.target 必须和后端实际端口一致
- 后端多次重启后端口会变（8000 → 8002 → 8003），要同步更新 proxy
- **数据没丢** — 44 个历史项目都还在 `projects/*.json` 里

---

## 11. Avoid common over-engineering

`ponytail: yagni` 默认开启。看到以下倾向就要警惕：
- 一次性写 5 个未来可能用到的引擎 → 删到当前 4 个
- 全局 CSS hack 解决多组件问题 → 改具体组件
- 通用 utility class 命名 `.btn-cinematic` / `.input-cinematic` — 保留，但不要每个新组件都造新 utility
- 复杂的撤销/重做栈 → V0 用浏览器自带 `Ctrl+Z` 即可
- 任何带 `creationflags=0x00000008` 之类的"防御性代码" → 实际是平台约束必须

---

## 12. When responding to user

- **诚实承认能力边界**。我猜了/没验证就直接说"已通过测试" → 用户立刻发现。改成"我做了 X，置信度是高/中/低"
- **不重复说"已 commit X"** 一次以上。说一次就够
- **直接给行动建议**而非 5 段"你可以考虑..."的废话
- **承认错的时候不绕弯**——"我之前的方案是 hack，正确的做法是 X"

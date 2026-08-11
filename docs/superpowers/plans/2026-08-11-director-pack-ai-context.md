# Director Pack GitHub AI Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a concise GitHub source-of-truth package that lets Web GPT and other Agents understand Video Forge's current capabilities, experimental Director Pack work, and recommended next steps without repeated user context.

**Architecture:** Keep one short AI entry document as the factual router, one Director Pack vision document for the two-layer product model, and one copy-ready Web GPT prompt. README links to the router instead of duplicating the full context; every capability is labeled as main, experimental, designed, or future.

**Tech Stack:** Markdown, Git, PowerShell validation commands

---

## File map

- Create `docs/START_HERE_FOR_AI.md`: authoritative, compact current-state router for Web GPT and new Agents.
- Create `docs/DIRECTOR_PACK_VISION.md`: public product model for declarative Director Packs and executable Visual Provider Packs.
- Create `.agent/web-gpt-product-review-prompt.md`: copy-ready prompt that tells Web GPT how to inspect GitHub and report evidence.
- Modify `README.md`: add the AI entry link near the top and correct the TTS/Agent capability summary without duplicating the new documents.
- Reference `docs/superpowers/specs/2026-08-11-director-pack-context-design.md`: approved design and status-language source.

### Task 1: Create the authoritative AI entry document

**Files:**
- Create: `docs/START_HERE_FOR_AI.md`
- Reference: `docs/AI_IMAGE_SCENE_PIPELINE.md`
- Reference: `docs/structured-content/agent-video-factory.md`

- [ ] **Step 1: Verify the file does not already exist**

Run:

```powershell
Test-Path docs/START_HERE_FOR_AI.md
```

Expected: `False`.

- [ ] **Step 2: Write the document with the exact responsibility boundaries**

The document must contain these sections in this order:

```markdown
# Video Forge：给 AI / Agent 的项目入口

## 一句话定位
## 状态标签
## AVAILABLE_ON_MAIN：现在能做什么
## 当前标准工作流
## 明确边界
## EXPERIMENTAL_BRANCH：已有实验但尚未上线
## DESIGNED / FUTURE：已设计与未来方向
## 关键文件导航
## 给新 Agent 的工作规则
## 如何取得新鲜验证证据
```

Use the four exact labels `AVAILABLE_ON_MAIN`, `EXPERIMENTAL_BRANCH`, `DESIGNED`, and `FUTURE`. List the five verified experimental branches by exact Git ref. State that external AI image calls and real paid Providers require user credentials and must not be claimed as tested without evidence.

- [ ] **Step 3: Check the document for required facts**

Run:

```powershell
$file = 'docs/START_HERE_FOR_AI.md'
$required = @(
  'AVAILABLE_ON_MAIN',
  'EXPERIMENTAL_BRANCH',
  'DESIGNED',
  'FUTURE',
  'codex/director-pack-studio-clean',
  'codex/code-visual-renderer-pack',
  'canonical timeline',
  'inputHash'
)
foreach ($value in $required) {
  if (-not (Select-String -LiteralPath $file -SimpleMatch $value -Quiet)) { throw "Missing: $value" }
}
```

Expected: exit code `0`, no output.

- [ ] **Step 4: Commit the factual router**

```powershell
git add -- docs/START_HERE_FOR_AI.md
git commit -m "docs: add AI project entry point"
```

### Task 2: Document the two-layer Director Pack model

**Files:**
- Create: `docs/DIRECTOR_PACK_VISION.md`
- Reference: `docs/superpowers/specs/2026-08-11-director-pack-context-design.md`

- [ ] **Step 1: Verify the file does not already exist**

Run:

```powershell
Test-Path docs/DIRECTOR_PACK_VISION.md
```

Expected: `False`.

- [ ] **Step 2: Write the public product vision**

The document must contain these sections:

```markdown
# Video Forge Director Pack 愿景

## 为什么需要导演包
## 两层模型
## Director Pack
## Visual Provider Pack
## 标准 Scene 请求与素材结果
## 典型组合
## 安全与版本边界
## 与 Pi Agent、Codex 和本地 Agent 的关系
## 当前状态
## 推荐集成顺序
```

Include a compact flow diagram. Explain that Director Packs are declarative and do not execute arbitrary code. Explain that Visual Provider Packs can generate SVG, PNG, transparent animation, or video but cannot change authoritative Scene timing. Mark current Director Studio and code-visual implementations as `EXPERIMENTAL_BRANCH`, not available on `main`.

- [ ] **Step 3: Validate the core separation**

Run:

```powershell
$file = 'docs/DIRECTOR_PACK_VISION.md'
$required = @(
  'Director Pack 不执行任意代码',
  'Visual Provider Pack',
  '不能改写 Scene 的权威时间',
  'EXPERIMENTAL_BRANCH',
  'stickman',
  'ai-image'
)
foreach ($value in $required) {
  if (-not (Select-String -LiteralPath $file -SimpleMatch $value -Quiet)) { throw "Missing: $value" }
}
```

Expected: exit code `0`, no output.

- [ ] **Step 4: Commit the vision document**

```powershell
git add -- docs/DIRECTOR_PACK_VISION.md
git commit -m "docs: define two-layer Director Pack model"
```

### Task 3: Create the Web GPT review prompt

**Files:**
- Create: `.agent/web-gpt-product-review-prompt.md`

- [ ] **Step 1: Verify the file does not already exist**

Run:

```powershell
Test-Path .agent/web-gpt-product-review-prompt.md
```

Expected: `False`.

- [ ] **Step 2: Write a copy-ready prompt**

The prompt must tell Web GPT to:

```text
1. Open https://github.com/Kvxw1105/video-forge and inspect the current main branch.
2. Read docs/START_HERE_FOR_AI.md first.
3. Read docs/DIRECTOR_PACK_VISION.md and docs/AI_IMAGE_SCENE_PIPELINE.md when relevant.
4. Separate observed facts, inferences, recommendations, and experimental-branch findings.
5. Cite the exact GitHub file or branch for important claims.
6. Never describe an experimental branch as shipped on main.
7. Produce: current capability map, user-visible gaps, highest-value next slice, risks, acceptance evidence, and questions that truly require the user.
8. Reuse GitHub context instead of asking the user to paste the project history again.
```

Do not hard-code a commit SHA, passing test count, API key, local private path, or personal Skill configuration.

- [ ] **Step 3: Scan the prompt for stable routing and prohibited stale facts**

Run:

```powershell
$file = '.agent/web-gpt-product-review-prompt.md'
$required = @('docs/START_HERE_FOR_AI.md', 'docs/DIRECTOR_PACK_VISION.md', 'observed facts', 'experimental branch')
foreach ($value in $required) {
  if (-not (Select-String -LiteralPath $file -SimpleMatch $value -Quiet)) { throw "Missing: $value" }
}
if (Select-String -LiteralPath $file -Pattern '\b[0-9a-f]{40}\b|sk-[A-Za-z0-9_-]{20,}' -Quiet) {
  throw 'Prompt contains a commit SHA or secret-like value'
}
```

Expected: exit code `0`, no output.

- [ ] **Step 4: Commit the prompt**

```powershell
git add -- .agent/web-gpt-product-review-prompt.md
git commit -m "docs: add Web GPT product review prompt"
```

### Task 4: Add the README entry and correct stale capability text

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Capture the current README anchors**

Run:

```powershell
rg -n '^# VideoForge|^## 核心功能|文案 → AI 配音|AI Agent 接口|AI 生图 Scene Pipeline' README.md
```

Expected: all five anchors are present.

- [ ] **Step 2: Add a compact AI/Agent entry after the opening description**

Add this block without copying the full capability map:

```markdown
> **给网页端 GPT / Codex / 其他 Agent：**先阅读 [AI 项目入口](docs/START_HERE_FOR_AI.md)。它区分 `main` 已实现能力、实验分支、已设计方向和未来设想，并提供继续分析所需的最短上下文。
```

Update the TTS capability row to list Edge TTS, Fish Audio, Volcengine, Manbo, custom API, and subtitle-only mode. Update the AI Agent row to mention API + CLI + MCP + Skill. Add one short link to `docs/DIRECTOR_PACK_VISION.md` below the AI image workflow, explicitly labeling it as a designed direction with experimental branch assets.

- [ ] **Step 3: Validate README links and language**

Run:

```powershell
$requiredPaths = @(
  'docs/START_HERE_FOR_AI.md',
  'docs/DIRECTOR_PACK_VISION.md',
  'docs/AI_IMAGE_SCENE_PIPELINE.md'
)
foreach ($path in $requiredPaths) {
  if (-not (Test-Path -LiteralPath $path)) { throw "Missing linked file: $path" }
  if (-not (Select-String -LiteralPath README.md -SimpleMatch $path -Quiet)) { throw "README does not link: $path" }
}
```

Expected: exit code `0`, no output.

- [ ] **Step 4: Commit the README change**

```powershell
git add -- README.md
git commit -m "docs: route Agents to authoritative context"
```

### Task 5: Cross-document verification and GitHub delivery

**Files:**
- Verify: `README.md`
- Verify: `docs/START_HERE_FOR_AI.md`
- Verify: `docs/DIRECTOR_PACK_VISION.md`
- Verify: `.agent/web-gpt-product-review-prompt.md`

- [ ] **Step 1: Run formatting and placeholder checks**

Run:

```powershell
git diff origin/main...HEAD --check
rg -n -i '\b(TBD|TODO|FIXME)\b|待补充' README.md docs/START_HERE_FOR_AI.md docs/DIRECTOR_PACK_VISION.md .agent/web-gpt-product-review-prompt.md
```

Expected: `git diff --check` exits `0`; `rg` returns no matches.

- [ ] **Step 2: Scan for secret-like values and private local content**

Run:

```powershell
rg -n 'sk-[A-Za-z0-9_-]{20,}|api[_-]?key\s*[:=]\s*\S+|C:\\Users\\' README.md docs/START_HERE_FOR_AI.md docs/DIRECTOR_PACK_VISION.md .agent/web-gpt-product-review-prompt.md
```

Expected: no matches.

- [ ] **Step 3: Validate every repository-relative Markdown link in the four files**

Run a PowerShell link scanner that extracts Markdown link targets not beginning with `http`, `#`, or `mailto:`, resolves each target relative to the source file, and throws when `Test-Path` is false.

Expected: exit code `0` and a summary showing every local link exists.

- [ ] **Step 4: Check status-language consistency**

Run:

```powershell
rg -n 'AVAILABLE_ON_MAIN|EXPERIMENTAL_BRANCH|DESIGNED|FUTURE' docs/START_HERE_FOR_AI.md docs/DIRECTOR_PACK_VISION.md
rg -n 'director-pack-studio-clean|code-visual-renderer-pack|stickman-visual-provider' docs/START_HERE_FOR_AI.md docs/DIRECTOR_PACK_VISION.md
```

Expected: status labels and experimental branch names are present in both documents where relevant.

- [ ] **Step 5: Verify Git state and push**

Run:

```powershell
git status --short --branch
git log --oneline -8
git fetch origin
git push origin main
git rev-parse HEAD
git rev-parse origin/main
```

Expected: worktree clean; push succeeds; local `HEAD` equals `origin/main`.

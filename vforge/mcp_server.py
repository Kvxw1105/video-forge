"""vforge MCP server — 让 AI Agent (Codex/Claude Code) 通过 MCP 协议接管 video-forge。

启动方式: `python -m vforge mcp`  →  stdio transport
        或: `vforge mcp`           →  同上
        或: 集成到 Claude Code config 见 SKILL.md

每个 tool 直接调用 client.py 中的 HTTP 函数。返回 JSON 字符串。
"""
import json
from typing import Any
from . import client

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:
    raise ImportError(
        "需要安装 mcp: pip install mcp\n"
        "然后运行: python -m vforge mcp"
    ) from e


def _to_json(obj: Any) -> dict:
    return json.dumps(obj, ensure_ascii=False, indent=2)


mcp = FastMCP(
    "video-forge",
    instructions=(
        "VideoForge — 自媒体视频自动化工作台。可创建项目、上传素材、"
        "生成 AI 配音、合成 MP4 预览、导出剪映草稿。所有操作基于 VideoForge 后端 HTTP API。"
    ),
)


@mcp.tool()
def health() -> dict:
    """检查 VideoForge 后端是否在线。"""
    return _to_json(client.health())


@mcp.tool()
def list_projects() -> dict:
    """列出所有视频项目。返回 [{id, name, created_at}, ...]"""
    return _to_json(client.list_projects())


@mcp.tool()
def create_project(name: str, ratio: str = "9:16", template_id: str | None = None) -> dict:
    """创建新项目。
    name: 项目名
    ratio: 画布比例，可选 "9:16"(抖音/小红书), "16:9"(B站), "1:1"(封面), "4:5"
    返回完整 project 对象，含 id。
    """
    return _to_json(client.create_project(name, ratio, template_id=template_id))


@mcp.tool()
def get_project(pid: str) -> dict:
    """获取项目完整数据：canvas/segments/assets/subtitles/audio/overlays。"""
    return _to_json(client.get_project(pid))


@mcp.tool()
def update_project(pid: str, data: dict) -> dict:
    """更新项目字段（深合并）。
    data 示例:
      {"canvas": {"background": {"type":"color","value":"#ffffff"}}}
      {"subtitles": [...]}
      {"segments": [...]}
    """
    return _to_json(client.update_project(pid, data))


@mcp.tool()
def delete_project(pid: str) -> dict:
    """删除项目（含所有素材和草稿）。"""
    return _to_json(client.delete_project(pid))


@mcp.tool()
def upload_asset(pid: str, file_path: str) -> dict:
    """上传本地文件到项目作为素材（图片/视频/音频）。
    file_path: 绝对路径。
    返回 {filename, name, path, type}。
    """
    return _to_json(client.upload_asset(pid, file_path))


@mcp.tool()
def generate_voiceover(pid: str, text: str, engine: str = "edge", speed: int = 0) -> dict:
    """生成 AI 配音并自动写回字幕。
    engine: "edge"(免费微软) / "manbo"(VIP,需配置) / "custom"(自定义) / "none"(只生成字幕)
    speed: -50~50
    返回 {audioPath, duration, subtitleCount, subtitles}。
    """
    return _to_json(client.generate_voiceover(pid, text, engine=engine, speed=speed))


@mcp.tool()
def import_srt(pid: str, file_path: str) -> dict:
    """从 .srt 文件导入字幕。"""
    return _to_json(client.import_srt(pid, file_path))


@mcp.tool()
def render_preview(pid: str) -> dict:
    """用 FFmpeg 合成 MP4 预览（图片+配音+BGM+字幕）。"""
    return _to_json(client.render_preview(pid))


@mcp.tool()
def export_jianying_zip(pid: str, output_path: str) -> dict:
    """导出剪映草稿为 ZIP 文件。"""
    return client.export_jianying_zip(pid, output_path)


@mcp.tool()
def export_jianying_direct(pid: str) -> dict:
    """直接写入本地剪映草稿目录（在剪映中可直接打开）。"""
    return _to_json(client.export_jianying_direct(pid))


@mcp.tool()
def jianying_status() -> dict:
    """查询本地剪映草稿目录是否被检测到。"""
    return _to_json(client.jianying_status())


@mcp.tool()
def list_templates() -> dict:
    """列出所有内置+用户模板。"""
    return _to_json(client.list_templates())


@mcp.tool()
def save_template(data: dict) -> dict:
    """把当前项目状态保存为模板。
    data: {"id":"tpl_xxx","name":"...","project_data":{...整个project}}
    """
    return _to_json(client.save_template(data))


@mcp.tool()
def get_tts_settings() -> dict:
    """获取 TTS 引擎配置（edge/manbo/custom 哪个启用，API key 等）。"""
    return _to_json(client.get_tts_settings())


@mcp.tool()
def update_tts_settings(data: dict) -> dict:
    """更新 TTS 引擎配置。"""
    return _to_json(client.update_tts_settings(data))


@mcp.tool()
def get_template(template_id: str) -> dict:
    """Read one reusable VideoForge template without changing any project."""
    return _to_json(client.get_template(template_id))


@mcp.tool()
def create_project_from_template(name: str, template_id: str, ratio: str = "9:16") -> dict:
    """Create one normal project from a template through the backend API."""
    return _to_json(client.create_project(name, ratio, template_id=template_id))


@mcp.tool()
def plan_template_batch(spec: dict) -> dict:
    """Validate a batch only. It creates no projects and never calls a provider."""
    return _to_json(client.plan_template_batch(spec))


@mcp.tool()
def start_template_batch(spec: dict) -> dict:
    """Start durable batch production. TTS is used only when explicitly selected in spec; unknown Sections are never guessed."""
    return _to_json(client.start_template_batch(spec))


@mcp.tool()
def list_template_batches() -> dict:
    """List persisted template production batches."""
    return _to_json(client.list_template_batches())


@mcp.tool()
def get_template_batch(batch_id: str) -> dict:
    """Read live aggregate state for one template batch without blocking."""
    return _to_json(client.get_template_batch(batch_id))


@mcp.tool()
def resume_template_batch(batch_id: str) -> dict:
    """Resume failed/interrupted items only; succeeded items are never re-executed."""
    return _to_json(client.resume_template_batch(batch_id))


@mcp.tool()
def get_template_batch_manifest(batch_id: str) -> dict:
    """Read the durable batch manifest through the backend API."""
    return _to_json(client.get_template_batch_manifest(batch_id))


@mcp.tool()
def get_visual_planning_context(pid: str) -> dict:
    """Read subtitle-timed narration units. Agent chooses semantics; backend owns time."""
    return _to_json(client.get_visual_planning_context(pid))

@mcp.tool()
def propose_visual_scene_plan(pid: str, settings: dict) -> dict:
    """Return deterministic scene candidates; it never writes a project."""
    return _to_json(client.propose_visual_scene_plan(pid, settings))

@mcp.tool()
def set_visual_scene_plan(pid: str, plan: dict, expected_updated_at: str | None = None) -> dict:
    """Persist explicit Agent scene groups after strict no-cross-Block validation."""
    return _to_json(client.set_visual_scene_plan(pid, plan, expected_updated_at))

@mcp.tool()
def get_visual_scene_plan(pid: str) -> dict: return _to_json(client.get_visual_scene_plan(pid))
@mcp.tool()
def validate_visual_scene_plan(pid: str) -> dict: return _to_json(client.validate_visual_scene_plan(pid))
@mcp.tool()
def set_visual_scene_prompt(pid: str, scene_id: str, prompt: str, negative_prompt: str = "") -> dict:
    """Update one Scene prompt through the validated HTTP visual-plan contract."""
    plan = client.get_visual_scene_plan(pid)
    if not plan or not plan.get("scenes"):
        raise ValueError("Visual plan not found")
    for scene in plan["scenes"]:
        if scene.get("id") == scene_id:
            scene["prompt"] = prompt
            scene["negativePrompt"] = negative_prompt
            return _to_json(client.set_visual_scene_plan(pid, plan))
    raise ValueError(f"Visual scene not found: {scene_id}")

@mcp.tool()
def attach_visual_scene_asset(pid: str, scene_id: str, asset_id: str) -> dict:
    """Attach an existing project asset; backend validates the saved Scene Plan."""
    plan = client.get_visual_scene_plan(pid)
    if not plan or not plan.get("scenes"):
        raise ValueError("Visual plan not found")
    for scene in plan["scenes"]:
        if scene.get("id") == scene_id:
            scene["visualAssetIds"] = [asset_id]
            scene["primaryAssetId"] = asset_id
            return _to_json(client.set_visual_scene_plan(pid, plan))
    raise ValueError(f"Visual scene not found: {scene_id}")


@mcp.tool()
def render_stickman_assets(
    pid: str,
    scene_ids: list[str] | None = None,
    export_png: bool = True,
    bind_to_project: bool = True,
    replace_manual_edits: bool = False,
) -> dict:
    """Render deterministic Stickman SVG/PNG assets from the project's Visual Plan."""
    return _to_json(client.render_stickman_assets(
        pid,
        scene_ids=scene_ids,
        export_png=export_png,
        bind_to_project=bind_to_project,
        replace_manual_edits=replace_manual_edits,
    ))


@mcp.tool()
def regenerate_stickman_scene(
    pid: str,
    scene_id: str,
    export_png: bool = True,
) -> dict:
    """Regenerate one Visual Scene without rewriting the other Scene outputs."""
    return _to_json(client.regenerate_stickman_scene(pid, scene_id, export_png=export_png))


@mcp.tool()
def get_stickman_generation_run(pid: str, run_id: str) -> dict:
    """Read manifest, report, and contact-sheet reference for one Stickman run."""
    return _to_json(client.get_stickman_generation_run(pid, run_id))


@mcp.tool()
def discover_mediakit() -> dict:
    """Discover the MediaKit Sidecar and its canonical local media capabilities."""
    return _to_json(client.discover_mediakit())


@mcp.tool()
def discover_media_providers() -> dict:
    """Discover VideoForge's native media engine and optional compatibility providers."""
    return _to_json(client.discover_media_providers())


@mcp.tool()
def execute_media_capability(pid: str, request: dict) -> dict:
    """Run media.probe, video.trim, or audio.extract and register a derived project asset."""
    return _to_json(client.execute_media(pid, request))


@mcp.tool()
def export_visual_generation_pack(pid: str) -> dict: return _to_json(client.export_visual_generation_pack(pid))
@mcp.tool()
def import_visual_scene_folder(pid: str, folder: str) -> dict: return _to_json(client.import_visual_scene_folder(pid, folder))
@mcp.tool()
def compile_visual_scene_variant(pid: str, variant_id: str) -> dict: return _to_json(client.compile_visual_scene_variant(pid, variant_id))

@mcp.tool()
def get_pending_visual_scenes(batch_id: str) -> dict: return _to_json(client.factory_pending_visuals(batch_id))
@mcp.tool()
def import_agent_video_item_visuals(batch_id: str, item_id: str, folder: str) -> dict: return _to_json(client.factory_import_visuals(batch_id,item_id,{"folder":folder}))
@mcp.tool()
def validate_agent_video_item_visuals(batch_id: str, item_id: str) -> dict: return _to_json(client.factory_validate_visuals(batch_id,item_id))
@mcp.tool()
def resume_agent_video_item(batch_id: str, item_id: str) -> dict: return _to_json(client.factory_resume_item(batch_id,item_id))
@mcp.tool()
def resume_agent_video_batch(batch_id: str) -> dict: return _to_json(client.factory_resume_batch(batch_id))
@mcp.tool()
def continue_agent_video_factory(batch_id: str) -> dict: return _to_json(client.factory_continue(batch_id))


@mcp.tool()
def list_structured_projects() -> dict:
    """List only projects with Structured Content."""
    return _to_json(client.list_structured_projects())


@mcp.tool()
def get_structured_project_status(pid: str) -> dict:
    """Return structured episode, composition, alignment, and updatedAt status."""
    return _to_json(client.get_structured_project_status(pid))


@mcp.tool()
def list_structured_variants(pid: str) -> dict:
    """List variants available in a Structured Episode."""
    return _to_json(client.list_structured_variants(pid))


@mcp.tool()
def compile_structured_variant_summary(pid: str, variant_id: str) -> dict:
    """Compile a read-only summary of one Structured Variant."""
    return _to_json(client.compile_structured_variant_summary(pid, variant_id))


@mcp.tool()
def parse_structured_markdown(text: str) -> dict:
    """Parse explicit Markdown/marker headings without writing a project or calling Fish."""
    return _to_json(client.parse_structured_markdown(text))


@mcp.tool()
def create_structured_project(name: str, episode: dict, ratio: str = "9:16") -> dict:
    """Create a Structured Project from user-confirmed Blocks and Variants."""
    return _to_json(client.create_structured_project(name, episode, ratio))


@mcp.tool()
def get_structured_episode_draft(pid: str) -> dict:
    """Read a Structured Episode draft through the backend API."""
    return _to_json(client.get_structured_episode_draft(pid))


@mcp.tool()
def update_structured_episode_draft(pid: str, data: dict, expected_updated_at: str | None = None) -> dict:
    """Update only an unaligned Structured Episode draft with optimistic concurrency protection."""
    return _to_json(client.update_structured_episode_draft(pid, data, expected_updated_at))


@mcp.tool()
def create_composition_project(name: str, ratio: str = "9:16") -> dict:
    """Create an empty Composition Project."""
    return _to_json(client.create_composition_project(name, ratio))


@mcp.tool()
def get_composition(pid: str) -> dict:
    """Read one Composition Project."""
    return _to_json(client.get_composition(pid))


@mcp.tool()
def set_composition_items(pid: str, items: list[dict], expected_updated_at: str | None = None) -> dict:
    """Replace Composition items after an optimistic updatedAt check."""
    return _to_json(client.set_composition_items(pid, items, expected_updated_at))


@mcp.tool()
def move_composition_item(pid: str, item_id: str, direction: str, expected_updated_at: str | None = None) -> dict:
    """Move one Composition item up or down."""
    return _to_json(client.move_composition_item(pid, item_id, direction, expected_updated_at))


@mcp.tool()
def set_composition_item_enabled(pid: str, item_id: str, enabled: bool, expected_updated_at: str | None = None) -> dict:
    """Enable or disable one Composition item."""
    return _to_json(client.set_composition_item_enabled(pid, item_id, enabled, expected_updated_at))


@mcp.tool()
def set_structured_block_enabled(pid: str, block_id: str, enabled: bool, expected_updated_at: str | None = None) -> dict:
    """Toggle only Block.enabled; never changes text, bindings, or audio."""
    return _to_json(client.set_structured_block_enabled(pid, block_id, enabled, expected_updated_at))


@mcp.tool()
def set_variant_block_order(pid: str, variant_id: str, block_ids: list[str], expected_updated_at: str | None = None) -> dict:
    """Set an existing Variant block order; IDs must exist and be unique."""
    return _to_json(client.set_variant_block_order(pid, variant_id, block_ids, expected_updated_at))


@mcp.tool()
def compile_composition(pid: str) -> dict:
    """Compile a Composition read-only summary."""
    return _to_json(client.compile_composition(pid))


@mcp.tool()
def preview_composition(pid: str) -> dict:
    """Generate a long-form Composition preview through the backend API."""
    return _to_json(client.preview_composition(pid))


@mcp.tool()
def export_composition_to_jianying(pid: str) -> dict:
    """Export a Composition to a new JianYing draft; replacement is not supported."""
    return _to_json(client.export_composition_to_jianying(pid))


def run(transport: str = "stdio", port: int = 8765):
    """Run the MCP server.
    transport: 'stdio' (default, for Claude Code/Codex stdio) or
               'streamable-http' (HTTP, for remote/networked clients)
    port: HTTP port when transport='streamable-http'
    """
    if transport == "streamable-http":
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = port
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run()

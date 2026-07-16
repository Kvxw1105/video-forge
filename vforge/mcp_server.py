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
def create_project(name: str, ratio: str = "9:16") -> dict:
    """创建新项目。
    name: 项目名
    ratio: 画布比例，可选 "9:16"(抖音/小红书), "16:9"(B站), "1:1"(封面), "4:5"
    返回完整 project 对象，含 id。
    """
    return _to_json(client.create_project(name, ratio))


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

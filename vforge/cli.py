"""vforge CLI — AI Agent 友好的命令行入口。

设计原则 (ponytail):
  - 单一脚本，stdlib only (argparse + json)
  - 每个子命令 < 30 行，输出 JSON 便于 Agent 解析
  - --base 参数让 Agent 指向任意后端（本地/远程）
"""
import argparse
import json
import sys
from pathlib import Path
from . import client


def _print(data, *, as_json: bool = True):
    """Print as JSON for Agent, or pretty for human."""
    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        if isinstance(data, (dict, list)):
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(data)


def cmd_health(args):
    _print(client.health(args.base))


def cmd_list(args):
    _print(client.list_projects(args.base))


def cmd_create(args):
    _print(client.create_project(args.name, args.ratio, args.base, args.template_id))


def cmd_get(args):
    _print(client.get_project(args.pid, args.base))


def cmd_update(args):
    """Update project. --data is a JSON string or @file.json path."""
    if args.data.startswith("@"):
        with open(args.data[1:], encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(args.data)
    _print(client.update_project(args.pid, data, args.base))


def cmd_delete(args):
    _print(client.delete_project(args.pid, args.base))


def cmd_upload(args):
    _print(client.upload_asset(args.pid, args.file, args.base))


def cmd_voiceover(args):
    _print(client.generate_voiceover(
        args.pid, args.text, engine=args.engine, speed=args.speed, base=args.base
    ))


def cmd_import_srt(args):
    _print(client.import_srt(args.pid, args.file, args.base))


def cmd_render(args):
    """Render MP4 preview. Optionally download to --output."""
    result = client.render_preview(args.pid, args.base)
    _print(result)
    if args.output and "previewUrl" in result:
        import urllib.request
        url = args.base.rstrip("/") + result["previewUrl"]
        with urllib.request.urlopen(url) as r, open(args.output, "wb") as f:
            f.write(r.read())
        print(f"\n[+] saved to {args.output}", file=sys.stderr)


def cmd_export_zip(args):
    """Export Jianying draft as ZIP."""
    path = client.export_jianying_zip(args.pid, args.output, args.base)
    print(f"[+] saved to {path}", file=sys.stderr)


def cmd_export_direct(args):
    """Export directly to local Jianying draft directory."""
    _print(client.export_jianying_direct(args.pid, args.base))


def cmd_jianying_status(args):
    _print(client.jianying_status(args.base))


def cmd_templates_list(args):
    _print(client.list_templates(args.base))


def cmd_template_save(args):
    """Save current project state as a template.
    --data is JSON like {"id": "tpl_xxx", "name": "...", "project_data": {...}}"""
    if args.data.startswith("@"):
        with open(args.data[1:], encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(args.data)
    _print(client.save_template(data, args.base))


def cmd_template_delete(args):
    _print(client.delete_template(args.tid, args.base))


def _spec(value: str) -> dict:
    if value.startswith("@"):
        with open(value[1:], encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(value)


def cmd_template_get(args): _print(client.get_template(args.template_id, args.base))
def cmd_batch_plan(args): _print(client.plan_template_batch(_spec(args.spec), args.base))
def cmd_batch_list(args): _print(client.list_template_batches(args.base))
def cmd_batch_status(args): _print(client.get_template_batch(args.batch_id, args.base))
def cmd_batch_manifest(args):
    result = client.get_template_batch_manifest(args.batch_id, args.base)
    if args.output:
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(result)


def _batch_start_or_resume(args, resume: bool = False):
    result = client.resume_template_batch(args.batch_id, args.base) if resume else client.start_template_batch(_spec(args.spec), args.base)
    if getattr(args, "wait", False):
        result = client.wait_template_batch(result["batchId"], base=args.base)
        _print(result)
        return 0 if result.get("status") == "succeeded" else 2 if result.get("status") == "partial" else 1
    _print(result); return 0


def cmd_batch_start(args): return _batch_start_or_resume(args)
def cmd_batch_resume(args): return _batch_start_or_resume(args, resume=True)
def cmd_visual_context(args): _print(client.get_visual_planning_context(args.pid,args.base))
def cmd_visual_propose(args): _print(client.propose_visual_scene_plan(args.pid,{"mode":args.mode,"targetDuration":args.target_duration,"unitsPerScene":args.units_per_scene},args.base))
def cmd_visual_set(args): _print(client.set_visual_scene_plan(args.pid,_spec(args.plan),base=args.base))
def cmd_visual_validate(args): _print(client.validate_visual_scene_plan(args.pid,args.base))
def cmd_visual_pack(args): _print(client.export_visual_generation_pack(args.pid,args.base))
def cmd_visual_import(args): _print(client.import_visual_scene_folder(args.pid,args.folder,args.base))
def cmd_visual_compile(args): _print(client.compile_visual_scene_variant(args.pid,args.variant_id,args.base))
def cmd_factory_pending(args): _print(client.factory_pending_visuals(args.batch_id,args.base))
def cmd_factory_import(args): _print(client.factory_import_visuals(args.batch_id,args.item_id,{"folder":args.folder},args.base))
def cmd_factory_validate(args): _print(client.factory_validate_visuals(args.batch_id,args.item_id,args.base))
def cmd_factory_resume_item(args): _print(client.factory_resume_item(args.batch_id,args.item_id,args.base))
def cmd_factory_resume(args): _print(client.factory_resume_batch(args.batch_id,args.base))
def cmd_factory_continue(args): _print(client.factory_continue(args.batch_id,args.base))


def cmd_tts_get(args):
    _print(client.get_tts_settings(args.base))


def cmd_tts_set(args):
    if args.data.startswith("@"):
        with open(args.data[1:], encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.loads(args.data)
    _print(client.update_tts_settings(data, args.base))


def cmd_run(args):
    """Run a multi-step workflow from a JSON file. Format:
    {"steps": [
       {"cmd": "create", "args": {"name": "demo"}},
       {"cmd": "upload", "args": {"pid": "$prev.id", "file": "..."}},
       ...
    ]}"""
    with open(args.workflow, encoding="utf-8") as f:
        wf = json.load(f)
    state = {}
    for i, step in enumerate(wf.get("steps", [])):
        cmd = step["cmd"]
        step_args = dict(step.get("args", {}))
        # Resolve $prev.x and $state.x references
        for k, v in list(step_args.items()):
            if isinstance(v, str) and v.startswith("$prev."):
                key = v.split(".", 1)[1]
                step_args[k] = state.get(key)
        # Dispatch
        fn = COMMAND_MAP.get(cmd)
        if not fn:
            raise SystemExit(f"step {i}: unknown cmd '{cmd}'")
        # Wrap to return result
        if cmd == "create":
            result = client.create_project(**step_args, base=args.base)
        elif cmd == "get":
            result = client.get_project(**step_args, base=args.base)
        elif cmd == "update":
            result = client.update_project(**step_args, base=args.base)
        elif cmd == "upload":
            result = client.upload_asset(**step_args, base=args.base)
        elif cmd == "voiceover":
            result = client.generate_voiceover(**step_args, base=args.base)
        elif cmd == "render":
            result = client.render_preview(**step_args, base=args.base)
        elif cmd == "export_zip":
            result = client.export_jianying_zip(**step_args, base=args.base)
        elif cmd == "export_direct":
            result = client.export_jianying_direct(**step_args, base=args.base)
        else:
            result = fn(args)
        # Store result for next steps
        if isinstance(result, dict):
            state = {**state, **result}
        print(f"step {i} ({cmd}): ok", file=sys.stderr)
    _print(state)


COMMAND_MAP = {
    "list": cmd_list, "create": cmd_create, "get": cmd_get, "update": cmd_update,
    "delete": cmd_delete, "upload": cmd_upload,
    "voiceover": cmd_voiceover, "import_srt": cmd_import_srt,
    "render": cmd_render, "export_zip": cmd_export_zip,
    "export_direct": cmd_export_direct, "jianying_status": cmd_jianying_status,
    "templates_list": cmd_templates_list, "template_save": cmd_template_save,
    "template_delete": cmd_template_delete,
    "template-get": cmd_template_get, "batch-plan": cmd_batch_plan,
    "batch-start": cmd_batch_start, "batch-list": cmd_batch_list,
    "batch-status": cmd_batch_status, "batch-resume": cmd_batch_resume,
    "batch-manifest": cmd_batch_manifest,
    "factory-pending-visuals": cmd_factory_pending, "factory-import-visuals": cmd_factory_import,
    "factory-validate-visuals": cmd_factory_validate, "factory-resume-item": cmd_factory_resume_item,
    "factory-resume": cmd_factory_resume, "factory-continue": cmd_factory_continue,
    "factory-plan": cmd_batch_plan, "factory-start": cmd_batch_start, "factory-status": cmd_batch_status,
    "factory-manifest": cmd_batch_manifest,
    "visual-context": cmd_visual_context, "visual-propose": cmd_visual_propose, "visual-set": cmd_visual_set,
    "visual-validate": cmd_visual_validate, "visual-pack": cmd_visual_pack, "visual-import": cmd_visual_import, "visual-compile": cmd_visual_compile,
    "tts_get": cmd_tts_get, "tts_set": cmd_tts_set,
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vforge",
        description="VideoForge CLI — AI Agent 友好的视频自动化工作台客户端",
    )
    p.add_argument("--base", default=client.DEFAULT_BASE,
                   help=f"后端 base URL (默认: {client.DEFAULT_BASE})")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(cmd_name, help, **kw):
        """Add a subcommand. Each kwarg key is the long flag (e.g. 'pid'), value
        is dict {flags: ['--pid'], type: str, required: True}. The flag gets
        a leading '--' automatically.
        """
        sp = sub.add_parser(cmd_name, help=help)
        sp.set_defaults(func=COMMAND_MAP.get(cmd_name))
        for k, v in kw.items():
            flag = v.pop("flag", f"--{k.replace('_', '-')}")
            sp.add_argument(flag, dest=k, **v)
        return sp

    sub.add_parser("health", help="健康检查").set_defaults(func=cmd_health)
    add("list", "列出所有项目")
    add("create", "创建项目",
        name={"type": str, "required": True},
        ratio={"type": str, "default": "9:16", "choices": ["9:16", "16:9", "1:1", "4:5", "4:3"]},
        template_id={"type": str, "default": None})
    add("get", "获取项目详情", pid={"type": str, "required": True})
    add("update", "更新项目（--data 是 JSON 字符串或 @file.json）",
        pid={"type": str, "required": True},
        data={"type": str, "required": True})
    add("delete", "删除项目", pid={"type": str, "required": True})
    add("upload", "上传素材到项目",
        pid={"type": str, "required": True},
        file={"type": str, "required": True})
    add("voiceover", "生成配音",
        pid={"type": str, "required": True},
        text={"type": str, "required": True},
        engine={"type": str, "default": "edge",
                "choices": ["edge", "manbo", "fish_audio", "custom", "none"]},
        speed={"type": int, "default": 0})
    add("import_srt", "导入 SRT 字幕",
        pid={"type": str, "required": True},
        file={"type": str, "required": True})
    add("render", "渲染 MP4 预览（可保存到 --output）",
        pid={"type": str, "required": True},
        output={"type": str, "default": ""})
    add("export_zip", "导出剪映草稿 ZIP",
        pid={"type": str, "required": True},
        output={"type": str, "required": True})
    add("export_direct", "直接导出到剪映草稿目录",
        pid={"type": str, "required": True})
    add("jianying_status", "查询剪映草稿目录状态")
    add("templates_list", "列出所有模板")
    add("template_save", "保存模板（--data 是 JSON）",
        data={"type": str, "required": True})
    add("template_delete", "删除模板",
        tid={"type": str, "required": True})
    add("template-get", "获取单个模板", template_id={"type": str, "required": True})
    add("batch-plan", "验证批次 Spec，不创建项目", spec={"type": str, "required": True})
    sp = add("batch-start", "启动模板批量产片", spec={"type": str, "required": True}); sp.add_argument("--wait", action="store_true")
    add("batch-list", "列出模板批次")
    add("batch-status", "读取批次状态", batch_id={"type": str, "required": True})
    sp = add("batch-resume", "恢复失败批次", batch_id={"type": str, "required": True}); sp.add_argument("--wait", action="store_true")
    add("batch-manifest", "读取批次 Manifest", batch_id={"type": str, "required": True}, output={"type": str, "default": ""})
    add("visual-context", "读取视觉分镜规划上下文", pid={"type": str, "required": True})
    add("visual-propose", "生成候选视觉分镜", pid={"type": str, "required": True}, mode={"type": str, "default": "target_duration", "choices":["fixed_units","target_duration","hybrid"]}, target_duration={"type": float, "default": 7.0}, units_per_scene={"type": int, "default": 3})
    add("visual-set", "保存明确视觉分镜", pid={"type": str, "required": True}, plan={"type": str, "required": True})
    add("visual-validate", "验证视觉分镜", pid={"type": str, "required": True})
    add("visual-pack", "导出视觉生成包", pid={"type": str, "required": True})
    add("visual-import", "从文件夹导入 Scene 素材", pid={"type": str, "required": True}, folder={"type": str, "required": True})
    add("visual-compile", "编译视觉分镜 Variant", pid={"type": str, "required": True}, variant_id={"type": str, "required": True})
    add("factory-pending-visuals", "读取待生成分镜", batch_id={"type": str, "required": True})
    add("factory-import-visuals", "导入分镜素材", batch_id={"type": str, "required": True}, item_id={"type": str, "required": True}, folder={"type": str, "required": True})
    add("factory-validate-visuals", "验证分镜素材", batch_id={"type": str, "required": True}, item_id={"type": str, "required": True})
    add("factory-resume-item", "恢复单项产片", batch_id={"type": str, "required": True}, item_id={"type": str, "required": True})
    add("factory-resume", "恢复批次", batch_id={"type": str, "required": True})
    add("factory-continue", "查询并继续工厂", batch_id={"type": str, "required": True})
    add("factory-plan", "验证工厂 Spec", spec={"type": str, "required": True})
    sp = add("factory-start", "启动工厂", spec={"type": str, "required": True}); sp.add_argument("--wait", action="store_true")
    add("factory-status", "读取工厂状态", batch_id={"type": str, "required": True})
    add("factory-manifest", "读取工厂 Manifest", batch_id={"type": str, "required": True}, output={"type": str, "default": ""})
    add("tts_get", "获取 TTS 设置")
    add("tts_set", "更新 TTS 设置（--data 是 JSON）",
        data={"type": str, "required": True})

    sub.add_parser("mcp", help="启动 MCP server (stdio)")\
        .set_defaults(func=lambda args: None)
    sp = sub.add_parser("mcp-http", help="启动 MCP server (HTTP transport)")
    sp.add_argument("--port", type=int, default=8765)
    sp.set_defaults(func=lambda args: None)
    sub.add_parser("serve", help="启动 MCP server (stdio, alias for mcp)")\
        .set_defaults(func=lambda args: None)

    sp = sub.add_parser("run", help="执行工作流 JSON 文件")
    sp.add_argument("workflow", help="workflow JSON 文件路径")
    sp.set_defaults(func=cmd_run)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd in ("mcp", "serve"):
        from . import mcp_server
        mcp_server.run(transport="stdio")
        return
    if args.cmd == "mcp-http":
        from . import mcp_server
        mcp_server.run(transport="streamable-http", port=getattr(args, "port", 8765))
        return
    try:
        result = args.func(args)
        if isinstance(result, int):
            return result
    except client.VForgeError as e:
        print(f"[!] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

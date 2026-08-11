from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(r"C:\Users\kvxkf\.codex\visualizations\2026\08\12\autonomous-video-factory-v3")
ROOT.mkdir(parents=True, exist_ok=True)


def main() -> None:
    console_errors: list[str] = []
    network_errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(record_video_dir=str(ROOT / "videos"), viewport={"width": 1440, "height": 1100})
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: console_errors.append(str(error)))
        page.on("response", lambda response: network_errors.append(f"{response.status} {response.url}") if response.status >= 400 else None)

        page.goto("http://127.0.0.1:5173/factory/new", wait_until="networkidle")
        page.get_by_label("视频名称").fill("V3 AUTO 浏览器验收")
        page.get_by_label("完整文案").fill("第一段解释一个常见知识现象。第二段说明它背后的因果关系。第三段给出可以执行的步骤。第四段总结如何把方法应用到日常工作中。")
        page.get_by_role("button", name="生成视频").click()
        page.screenshot(path=str(ROOT / "01-auto-start.png"), full_page=True)
        page.wait_for_timeout(1000)
        auto_state = ""
        for _ in range(180):
            auto_state = page.locator("body").inner_text()
            if "视频生产完成" in auto_state or "无法" in auto_state or "失败" in auto_state:
                break
            page.wait_for_timeout(1000)
        page.screenshot(path=str(ROOT / "02-auto-finished.png"), full_page=True)

        page.goto("http://127.0.0.1:5173/factory/new", wait_until="networkidle")
        page.get_by_label("视频名称").fill("V3 REVIEW 浏览器验收")
        page.get_by_label("完整文案").fill("心理认知中的第一个误区。它会制造一个错误的判断。通过三个步骤可以重新检查这个判断。最后把方法应用到下一次选择。")
        page.get_by_role("button", name="REVIEW：批量审查视觉").click()
        page.get_by_label("配音引擎").select_option("none")
        page.get_by_role("button", name="生成视频").click()
        review_state = ""
        review_reached = False
        for _ in range(120):
            review_state = page.locator("body").inner_text()
            if "REVIEW ALL VISUALS" in review_state or "无法" in review_state or "失败" in review_state:
                review_reached = "REVIEW ALL VISUALS" in review_state
                break
            page.wait_for_timeout(1000)
        page.screenshot(path=str(ROOT / "03-review-candidates.png"), full_page=True)
        if review_reached:
            page.get_by_role("button", name="Approve & Continue").click()
            for _ in range(120):
                review_state = page.locator("body").inner_text()
                if "Preview 和剪映草稿已生成" in review_state or "视频生产完成" in review_state or "Batch " in review_state and "succeeded" in review_state or "失败" in review_state:
                    break
                page.wait_for_timeout(1000)
            page.screenshot(path=str(ROOT / "04-review-succeeded.png"), full_page=True)
            if "succeeded" in review_state:
                page.locator("textarea").first.fill("心理认知中的第一个误区已改写，但保留原 Scene 时间窗。")
                page.get_by_role("button", name="保存文本并增量重跑").click()
                for _ in range(120):
                    review_state = page.locator("body").inner_text()
                    if "时间轴保持不变" in review_state or "REVIEW ALL VISUALS" in review_state or "失败" in review_state:
                        break
                    page.wait_for_timeout(1000)
                page.screenshot(path=str(ROOT / "05-incremental-rerun.png"), full_page=True)
                if "REVIEW ALL VISUALS" in review_state:
                    page.get_by_role("button", name="Approve & Continue").click()
                    for _ in range(120):
                        review_state = page.locator("body").inner_text()
                        if "succeeded" in review_state or "失败" in review_state:
                            break
                        page.wait_for_timeout(1000)
                    page.screenshot(path=str(ROOT / "06-incremental-succeeded.png"), full_page=True)

        context.tracing.stop(path=str(ROOT / "v3-browser-trace.zip"))
        context.close()
        browser.close()
    result = {"autoCompleted": "视频生产完成" in auto_state, "reviewReached": review_reached, "reviewCompleted": "Batch " in review_state and "succeeded" in review_state, "consoleErrors": console_errors, "networkErrors": [item for item in network_errors if not item.startswith("404 http://127.0.0.1:5173/@")], "evidence": str(ROOT)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

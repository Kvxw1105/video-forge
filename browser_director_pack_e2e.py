from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


BASE = "http://127.0.0.1:5173"
EVIDENCE = Path(r"C:\Users\kvxkf\.codex\visualizations\2026\08\13\director-pack-protocol-v1")
EVIDENCE.mkdir(parents=True, exist_ok=True)


def wait_batch(page: Page, batch_id: str, states: set[str], timeout: float = 240) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        response = page.request.get(f"{BASE}/api/batches/template-production/{batch_id}")
        if response.ok:
            last = response.json()
            item = (last.get("items") or [{}])[0]
            if item.get("status") in states:
                return last
        page.wait_for_timeout(750)
    raise AssertionError(f"batch {batch_id} did not reach {sorted(states)}; last={last}")


def choose_pack(page: Page) -> None:
    page.get_by_role("button", name=re.compile("Knowledge Cinematic")).first.click()


def start_factory(page: Page, name: str, mode: str) -> dict[str, Any]:
    page.goto(f"{BASE}/factory/new", wait_until="networkidle")
    page.get_by_test_id("factory-name").fill(name)
    page.get_by_test_id("factory-script").fill(
        "## MECHANISM\n"
        "这个机制的原因会导致一个明确结果。\n"
        "整个流程分为三个步骤，系统结构决定最后的因果关系。\n\n"
        "## STORY\n"
        "一个人物面对心理冲突，必须做出选择。\n"
        "两个人的关系在压力和情绪中发生拉扯。\n\n"
        "## METHOD\n"
        "三个关键数据分别是百分之二十、百分之五十和百分之八十。"
    )
    choose_pack(page)
    page.get_by_label("配音引擎").select_option("none")
    page.get_by_test_id("mode-review" if mode == "review" else "mode-auto").click()
    with page.expect_response(
        lambda response: response.url.endswith("/api/batches/template-production")
        and response.request.method == "POST",
        timeout=30_000,
    ) as response_info:
        page.get_by_test_id("factory-start").click()
    response = response_info.value
    assert response.ok, response.text()
    assert page.get_by_test_id("factory-start").count() == 0 or page.get_by_test_id("factory-start").is_disabled()
    return response.json()


def ffprobe(path: str) -> dict[str, Any]:
    command = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height",
        "-of", "json", path,
    ]
    return json.loads(subprocess.check_output(command, text=True, encoding="utf-8"))


def main() -> None:
    console_errors: list[str] = []
    page_errors: list[str] = []
    network_errors: list[str] = []
    results: dict[str, Any] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100},
            accept_downloads=True,
            record_video_dir=str(EVIDENCE / "videos"),
        )
        context.tracing.start(screenshots=True, snapshots=True, sources=True)
        page = context.new_page()
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        page.on("response", lambda response: network_errors.append(f"{response.status} {response.url}") if response.status >= 500 else None)

        page.goto(f"{BASE}/director-packs", wait_until="networkidle")
        page.get_by_role("heading", name="Knowledge Cinematic").wait_for(timeout=20_000)
        references = page.locator('img[alt$="参考模板"]')
        assert references.count() >= 3
        for index in range(references.count()):
            references.nth(index).wait_for(state="visible")
            image_state = references.nth(index).evaluate(
                "image => ({src: image.src, complete: image.complete, width: image.naturalWidth, height: image.naturalHeight})"
            )
            print(json.dumps({"referenceImage": image_state}, ensure_ascii=False), flush=True)
            assert image_state["complete"] and image_state["width"] > 0, image_state
        body = page.locator("body").inner_text()
        assert "code_visual" in body and "stickman" in body
        page.screenshot(path=str(EVIDENCE / "01-pack-detail.png"), full_page=True)

        with page.expect_download() as download_info:
            page.get_by_role("button", name="导出").click()
        exported = Path(download_info.value.path())
        assert exported.read_bytes()[:2] == b"PK"
        page.locator('input[type="file"]').set_input_files(str(exported))
        page.wait_for_timeout(1000)
        assert "导演包导入失败" not in page.locator("body").inner_text()

        derived_id = f"kvxw/knowledge-cinematic-e2e-{int(time.time())}"
        page.get_by_role("button", name="复制并派生").click()
        page.get_by_label("新 ID").fill(derived_id)
        page.get_by_label("版本").fill("0.1.0")
        page.get_by_label("风格锚点").fill("cinematic editorial, warm paper, restrained contrast, e2e derived")
        page.get_by_role("button", name="保存派生包").click()
        page.get_by_text(derived_id, exact=False).first.wait_for(timeout=20_000)
        page.screenshot(path=str(EVIDENCE / "02-derived-pack.png"), full_page=True)
        results["manager"] = {"references": references.count(), "exportedBytes": exported.stat().st_size, "derivedId": derived_id}

        auto_start = start_factory(page, "Director Pack AUTO 浏览器验收", "auto")
        auto_batch = wait_batch(page, auto_start["batchId"], {"succeeded", "failed"})
        auto_item = auto_batch["items"][0]
        assert auto_item["status"] == "succeeded", auto_item.get("error")
        auto_visuals = page.request.get(
            f"{BASE}/api/agent-factory/batches/{auto_batch['batchId']}/items/{auto_item['itemId']}/visuals"
        ).json()
        providers = {
            item.get("providerId")
            for visual_batch in auto_visuals.get("visualBatches", [])
            for item in visual_batch.get("items", [])
        }
        assert {"code_visual", "stickman"} <= providers, providers
        assert auto_visuals["coverage"]["complete"] is True
        snapshot = auto_item["resolvedDirectorPolicy"]
        assert snapshot["pack"]["id"] == "kvxw/knowledge-cinematic"
        assert snapshot["pack"]["manifestDigest"].startswith("sha256:")
        page.get_by_test_id("factory-complete").wait_for(timeout=20_000)
        page.screenshot(path=str(EVIDENCE / "03-auto-complete.png"), full_page=True)

        preview_path = auto_item["outputs"]["preview"]["path"]
        probe = ffprobe(preview_path)
        assert any(stream.get("codec_type") == "video" for stream in probe.get("streams", []))
        draft_path = Path(auto_item["outputs"]["jianying"]["draftPath"])
        assert (draft_path / "draft_content.json").is_file()
        results["auto"] = {
            "batchId": auto_batch["batchId"],
            "projectId": auto_item["projectId"],
            "providers": sorted(providers),
            "coverage": auto_visuals["coverage"],
            "manifestDigest": snapshot["pack"]["manifestDigest"],
            "previewPath": preview_path,
            "ffprobe": probe,
            "jianyingDraftPath": str(draft_path),
            "jianying": "JY_STRUCTURE_VERIFIED",
        }

        review_start = start_factory(page, "Director Pack REVIEW 浏览器验收", "review")
        review_batch = wait_batch(page, review_start["batchId"], {"awaiting_visual_approval", "failed"})
        review_item = review_batch["items"][0]
        assert review_item["status"] == "awaiting_visual_approval", review_item.get("error")
        page.wait_for_url("**/factory/batches/**/visuals", timeout=30_000)
        page.get_by_text("REVIEW ALL VISUALS", exact=True).wait_for(timeout=30_000)
        candidates = page.locator('img[alt="candidate"]')
        assert candidates.count() >= 3
        candidate_count = candidates.count()
        if candidate_count > 1:
            candidates.nth(1).locator("xpath=..").click()
        page.screenshot(path=str(EVIDENCE / "04-review-candidates.png"), full_page=True)
        page.get_by_role("button", name="Approve & Continue").click()
        review_done = wait_batch(page, review_batch["batchId"], {"succeeded", "failed"})
        assert review_done["items"][0]["status"] == "succeeded", review_done["items"][0].get("error")
        page.screenshot(path=str(EVIDENCE / "05-review-complete.png"), full_page=True)
        results["review"] = {
            "batchId": review_batch["batchId"],
            "candidateImages": candidate_count,
            "status": review_done["items"][0]["status"],
        }

        context.tracing.stop(path=str(EVIDENCE / "director-pack-browser-trace.zip"))
        context.close()
        browser.close()

    results["consoleErrors"] = console_errors
    results["pageErrors"] = page_errors
    results["network5xx"] = network_errors
    results["evidence"] = str(EVIDENCE)
    results["jianyingGui"] = "JY_GUI_NOT_VERIFIED"
    (EVIDENCE / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False))
    if console_errors or page_errors or network_errors:
        raise AssertionError({"console": console_errors, "page": page_errors, "network5xx": network_errors})


if __name__ == "__main__":
    main()

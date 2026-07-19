# Single-process production runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Serve the built React SPA and existing FastAPI API from one local Python launcher without changing development mode.

**Architecture:** `main.create_app()` remains the API composition point and optionally mounts a validated frontend dist. `backend/launcher.py` validates the build, selects a loopback port, optionally opens the browser, and runs Uvicorn. PowerShell scripts wrap build and launch commands.

**Tech Stack:** FastAPI, Starlette `StaticFiles`/`FileResponse`, Uvicorn, React/Vite, PowerShell, pytest.

---

Tests cover API precedence, SPA deep links, static asset 404s, traversal rejection, missing builds, port selection, and launcher error messages. The existing `python -m uvicorn main:app` path remains unchanged.

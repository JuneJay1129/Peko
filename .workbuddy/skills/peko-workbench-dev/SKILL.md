---
name: peko-workbench-dev
description: Project-specific development guide for the Peko desktop pet (PyQt5) and its personal planning workspace. This skill should be used when developing, modifying, or debugging Peko's 桌宠/desktop-pet features, the 工作台/计划台 workspace page (plans_web.html), the plans_store data layer, the workbench_server sync API, tray integration, or implementing pet-workspace linkage (C5 natural-language entry, B3 completion feedback, reminders, companion state). Covers the architecture map, three runtime modes, add-module SOP, coding conventions, test commands, and known pitfalls.
agent_created: true
---

# Peko Workbench Dev

## Overview

Peko is a PyQt5 desktop pet (桌宠) with two feature groups: interactive chat and a 6-module personal planning workspace (工作台). The workspace is a single-file HTML page shown in two shapes — an embedded tray window (计划台) and a browser-opened web version (工作台) — that share one local data set and stay in sync. Use this skill to develop or modify any of this without re-discovering the architecture, conventions, or test setup each session.

Read `references/architecture.md` for the full file/data/API map, `references/conventions.md` for coding rules, and `references/linkage-roadmap.md` for the pet-workspace linkage plan. This SKILL.md holds only the essential procedures.

## Golden rules (do these every time)

1. Fix the caller / task side, not shared utils — avoid impacting other callers.
2. Keep the workspace zero-dependency, single-file HTML, all CSS/JS inline, light theme, SVG icons (no emoji), Chinese UI.
3. After editing `peko/core/plans_store.py`, run `py_compile` and grep to confirm there is exactly ONE `class PlansStore:` (a duplicate class silently shadows the original and drops plans/todos methods).
4. After editing the inline `<script>` in `plans_web.html`, extract it and run `node --check` (a stray `}); });` double-close once broke the whole script and forced all modes into `local`).
5. The local sync server must run on SYSTEM Python (`C:/Users/502380/AppData/Local/Programs/Python/Python313/python.exe`) — it is the only env with PyQt5. Do NOT start it under a managed venv.

## Architecture map (quick)

| Piece | Path | Role |
| --- | --- | --- |
| Single source of truth | `peko/core/plans_store.py` | Atomic write (temp + `os.replace`); `plans/todos/habits/ledger/review/focus_log()` + `replace_*`; `_normalize_*` |
| Sync server | `peko/ui/workbench_server.py` | `ThreadingHTTPServer` @ `127.0.0.1:18340`; `GET/POST /api/plans|todos|habits|ledger|review|focus` |
| Workspace page | `peko/ui/plans/plans_web.html` | 6 modules; `bridge`/`http`/`local` modes; `STATE` holds all arrays |
| Tray entry | `peko/ui/tray.py` | 托盘「计划台」→embedded; 托盘「工作台」→browser |
| Bridge | `PlanBridge` (QWebChannel) | `getAll/save/getTodos/saveTodos` for the embedded window |

Data files (all `{version, items}`): `data/plans.json`, `todos.json`, `habits.json`, `ledger.json`, `review.json`, `focus.json`.

## Three runtime modes

`plans_web.html` self-detects and branches all persistence through it:

- `bridge` — embedded QWebEngineView via QWebChannel `PlanBridge`.
- `http` — browser at `127.0.0.1:18340`; reads/writes `/api/*`. Detected by `location.hostname === "127.0.0.1" || "localhost"`.
- `local` — `file://` fallback → localStorage (keys like `wb_wb_habits`).

Embedded gating: `body.embedded` hides `.tab-ext`, `#btnAddHabit`, `#btnAddLedger`, and edit/import/export/clear — the embedded window keeps only 计划台/待办清单 view + complete. Extension modules are editable only in the browser web version.

## SOP: add a new workspace module

1. Data layer — in `plans_store.py` add `_normalize_X`, wire `_load_named`/`_persist_named`, expose `X()` + `replace_X()`. Create `data/X.json` shape `{version, items}`.
2. Server — in `workbench_server.py` add `GET /api/X` and include `/api/X` in the POST dispatch to `replace_X`.
3. Front end — in `plans_web.html`: add the array to `STATE`; add `persistX` (http→`/api/X`, local→localStorage); add the fetch to `loadAll`/`doRefresh` `Promise.all`; add a tab + `<section id="mod-X">` + its render function.
4. Embedded gating — if it is an extension module, mark its tab `.tab-ext` and hide its add button under `body.embedded`.
5. Seed + export — add example seed entries; include the array in export (`version:2`).
6. Test all three modes (below) before declaring done.

## SOP: implement a pet-workspace linkage

Follow `references/linkage-roadmap.md`. Priority order: C5 (natural-language entry → write to a module via `plans_store` or `/api/*`) then B3 (workspace completion → pet mood/achievement feedback), then A (reminder + jump) and D (companion state). Desktop-side work lives in `peko/ui/tray.py` + `PlanBridge`; always land data through `plans_store`/`workbench_server`, never bypass them.

## Testing

Headless jsdom regression covers all three modes: `scripts/wb_modes_test.js`.

- Use managed Node: `C:/Users/502380/.workbuddy/binaries/node/versions/22.22.2/node.exe`.
- jsdom lives in `C:/Users/502380/.workbuddy/binaries/node/workspace/node_modules`; set `NODE_PATH` with WINDOWS BACKSLASHES (forward slashes fail to resolve).
- Start the local server first on SYSTEM Python via `scripts/_wb_server_runner.py`.

Run:

```bash
NODE_PATH="C:\\Users\\502380\\.workbuddy\\binaries\\node\\workspace\\node_modules" node scripts/wb_modes_test.js
```

## Known pitfalls

- Duplicate `class PlansStore:` after an edit → methods silently lost. Verify with grep + `py_compile`.
- `}); });` double-close in the inline script → entire JS dead, all modes fall to `local`. `node --check` the extracted script.
- `NODE_PATH` with forward slashes → `Cannot find module 'jsdom'`. Use backslashes.
- `/tmp/...` does not exist on Windows → put temp check files under `scripts/` and delete after.
- Git hygiene: `data/*.json`, `data/chat_history/*`, `.workbuddy/*` were once staged by mistake and `.gitignore` lacks `data/` + `.workbuddy/` rules. Add ignore rules and clean the index before committing.
- Offscreen Qt tests (`QT_QPA_PLATFORM=offscreen`): if a dialog is the last visible window, closing it triggers `quitOnLastWindowClosed` → the event loop exits early and all later QTimers silently never fire (zero-ms timers still fire, which misleads debugging). Always `app.setQuitOnLastWindowClosed(False)` + `pet.show()` in widget tests. Symptom: flow stalls right after a dialog closes with no error.
- Pet registry id ≠ folder name: `pets/BB/pet_config.json` has `id: "hamster"`, so use `get_pet("hamster")`, not `get_pet("BB")`.
- Qt-dependent tests need SYSTEM Python (only it has PyQt5); guard with `try: import PyQt5` + `@unittest.skipUnless` so the managed-Python suite still collects cleanly.
- File deletion from a WorkBuddy-spawned process is intercepted by a shim (`SAFE_DELETE_FAIL_CLOSED`) — send2trash/os.remove appear to fail even with sandbox bypass. For delete-style features, surface the real error (console print + bubble) and have the user verify from a NORMAL terminal. send2trash's modern (IFileOperation) path can itself fail on some machines → fall back to PowerShell `Microsoft.VisualBasic.FileIO.FileSystem.DeleteFile(path, 'OnlyErrorDialogs', 'SendToRecycleBin')`.
- Animating the pet across the screen: walk states also move the pet per frame tick (`update_position`), which stacks with `QPropertyAnimation(pos)` and overshoots. Freeze the state's `moveSpeed` in `pet._state_config` during the scripted move and restore after.
- Offscreen Qt test screens are small — position assertions must replicate the implementation's screen-edge clamping.

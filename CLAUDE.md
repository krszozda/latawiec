# Latawiec — working rules

Server-driven UI framework: Python DSL → DivKit JSON → native shells.
`sdk-python/` holds the `latawiec` package; native shells will live in `shell-android/`
and `shell-ios/`.

## Code

- Code, comments, commits, and docs are in English.
- Smallest API that works. No speculative abstractions, no code "for later".
- Comments only for what the code cannot say (external quirks, non-obvious constraints).
  Never narrate the code.
- Tests assert contracts — the exact JSON a component renders to — not mere existence.
- The DSL never hand-writes DivKit JSON. It builds `pydivkit` models and serializes
  through them, so the output always matches the DivKit schema.

## Process

- Conventional Commits, one logical change per commit.
- Before every commit, run the `slop-reviewer` agent on the diff and fix its findings.
- Feature work happens on branches and lands via PR; the maintainer merges.
- Must pass before pushing (run in `sdk-python/`):
  `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest`
- When `shell-android/` changed, it must also build: `./gradlew :app:assembleDebug`.
- When `shell-ios/` changed, it must also build: `xcodegen generate && xcodebuild
  -project LatawiecShell.xcodeproj -scheme LatawiecShell -destination
  'generic/platform=iOS Simulator' build` in `shell-ios/`. The UI tests
  (`xcodebuild test` on a booted simulator; `connectedDebugAndroidTest` on a
  running emulator) need five servers from `sdk-python/`: `examples.hello` on
  port 8000, `examples.tabs` on port 8001, `examples.auth` on port 8002,
  `examples.prod` on port 8004, and `examples.live` on port 8005.
  Run `xcodebuild test` without CODE_SIGNING_ALLOWED=NO: an unsigned build
  cannot write the Keychain (-34018) and the auth test fails on it.
- DivKit APIs are verified against the published artifacts (javap on the Android AAR
  classes, the tagged divkit-ios sources) before use, not written from memory.
- Shell apps stay near native weight: Android release builds are minified and
  resource-shrunk, and CI enforces an APK size budget (3 MB). A change that needs
  a bigger budget is discussed in its PR, never slipped in.

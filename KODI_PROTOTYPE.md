# LitePlayer Kodi native build prototype

This branch is isolated from the existing ExoPlayer-based LitePlayer on `main`.

## What is implemented

- A GitHub Actions Android native Kodi build workflow, adapted from [thecordcutter/kodi-apk-builder](https://github.com/thecordcutter/kodi-apk-builder).
- Defaults: app label `LitePlayer`, Android package `com.example.liteplayer`, APK name `LitePlayer.apk`, and arm64-v8a.
- The workflow downloads and builds actual Kodi source and its native VideoPlayer engine.

## Not yet implemented or verified

- Launching a Plezy-supplied URI directly into playback without Kodi's home screen.
- Returning directly to Plezy after stopping or finishing.
- Plezy next-episode handoff and subtitle automation.
- A successful Kodi APK build on GitHub Actions or a Shield TV playback test.

This is **not yet a playback-only LitePlayer**. Do not install it expecting Plezy integration.

## Why a separate branch?

The original LitePlayer code, workflow and saved APKs on `main` remain untouched.

The upstream builder describes itself as experimental and unmaintained. The workflow has not been tested in this repository. It is licensed according to the upstream project's terms and Kodi's applicable GPL obligations.

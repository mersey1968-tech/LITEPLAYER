# LitePlayer public launch checklist

- [x] Preserve user-tested buffered source on its own stable branch
- [x] Prepare product description, release notes, community posts, reviewer email and demo script
- [ ] Validate the actual installable package against the preserved source commit
- [ ] **LEGAL BLOCKER:** Resolve possible GPL-2.0-only versus GPL-3.0-only incompatibility between Jellyfin-derived IEC adaptations and NextLib. See `launch/LEGAL_AUDIT_2026-11-21.md`.
- [ ] Review distribution rights and notices for FFmpeg-derived IEC code, Jellyfin-derived adaptations, jcifs-ng, AndroidX and bundled extensions; verify exact APK dependency tree and corresponding source
- [ ] Choose final application ID, app label, icon and version with no unintended conflict with installed builds
- [ ] Generate a durable release signing key; store it securely outside public GitHub (never share a private key in the repo)
- [ ] Build a signed release APK and verify signatures and installation on Shield
- [ ] Verify SDR, HDR10, compatible Dolby Vision profiles, AFR, major audio codecs, SMB and external-launcher integration on actual hardware
- [ ] Capture accurate screenshots and a real-device demonstration
- [ ] Publish binary, SHA-256 checksum, license/notice files, installation instructions and notes in a GitHub Release
- [ ] Get owner's approval before posting to forums or contacting reviewers
- [ ] Publish announcement posts following community self-promotion policies
- [ ] Collect compatibility reports, and avoid changing the stable playback engine without a regression test

# Release checklist

Baseline: RC1 / AFRFirst, commit 2d5b19a3774bfae40406cdda5ee3125a23e4a59d. Keep the approved 720p and 1080p processing unchanged. Do not merge into LitePlayer main.

- [x] Preserve tested baseline in separate branch.
- [ ] Audit exact build inputs, original code provenance, dependency versions and packaged assets.
- [ ] Verify third-party copyright notices, license texts, GPL/LGPL corresponding source and applicable installation/relinking requirements.
- [ ] Review codec patent and trademark obligations, including the Reflite name.
- [ ] Decide compatible distribution license with rights holder; do not publish incomplete license declarations.
- [ ] Verify signing and production package configuration, reproducible build instructions and APK checksum.
- [ ] Test SDR, HDR10, Dolby Vision, AFR, audio passthrough, subtitles, SMB and external player behavior.
- [ ] Prepare privacy policy and data safety disclosures; verify actual network behavior.
- [ ] Confirm current Google Play TV requirements before Play submission.
- [ ] Publish approved public release artifact only after compliance review.

Known issue: minor 1080p startup hitch before synchronization rewind. The optimized experiment was rejected; RC1 remains the reference.

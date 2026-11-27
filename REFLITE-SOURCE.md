# RC1 source and build provenance

The approved RC1 is the AFRFirst APK, renamed without rebuilding.

- Exact application revision: https://github.com/mersey1968-tech/LITEPLAYER/tree/2d5b19a3774bfae40406cdda5ee3125a23e4a59d
- Source archive: https://github.com/mersey1968-tech/LITEPLAYER/archive/2d5b19a3774bfae40406cdda5ee3125a23e4a59d.zip
- Build recipe: https://github.com/mersey1968-tech/LITEPLAYER/blob/2d5b19a3774bfae40406cdda5ee3125a23e4a59d/.github/workflows/reflite-gpu.yml
- Original CI run: https://github.com/mersey1968-tech/LITEPLAYER/actions/runs/46052196729

The recipe unpacks LitePlayer.zip, overlays source-review files, applies the research patches, then builds using JDK 17, Gradle 8.9 and Android SDK. Consult the pinned workflow for the exact sequence.

This is an application-source pointer, NOT yet a complete GPL corresponding-source package. The original application and IEC code ownership, exact native FFmpeg configuration, full dependency closure, third-party license texts and any installation/relinking information remain subject to verification. No public binary release is authorized by this document.

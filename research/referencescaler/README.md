# ReferenceScaler — isolated research shader

**Status:** Design experiment only. NOT connected to LitePlayer playback, and not benchmarked against madVR, Shield AI, or Sony. No APK is built by this branch.

## Scope
- SDR RGB 1080p to 2160p scaling research.
- Two-pass separable 6-tap Kaiser-windowed sinc, cutoff 0.96 and beta 7.5.
- Configurable anti-ringing containment, uRingingClamp = 0..1.0.
- No sharpening, super-resolution, contrast or colour enhancement.
- Identical processing on all RGB channels in their input transfer encoding.

## Integration limits
LitePlayer currently uses MediaCodec via SurfaceView; it cannot feed this GLSL sampler without adding a separate decoder-to-GPU image path, such as an external texture with a SurfaceTexture / OpenGL ES pipeline. That would be an independent render path and requires rigorous validation of decoder timing, latency, colour range, video synchronisation and automatic frame rate switching. **No existing player files or workflows have been modified in this branch.**

This shader expects already-decoded SDR RGB data from a normal texture and is NOT a direct plug-in for MediaCodec's protected decoder SurfaceView. HDR10 and Dolby Vision must bypass the shader unchanged until an explicitly verified HDR pipeline exists. Using 2D RGB textures for YUV material requires accurate colour matrix and range conversion. Proper linear-light scaling would require explicit calibrated transfer-function decode / encode and significantly more GPU bandwidth and precision; this prototype does NOT claim linear-light correctness.

## Proposed objective evaluation
1. Compare Lanczos2, windowed-sinc and monotonic reconstruction against photographic / zone-plate / diagonal-line images with known ground-truth 4K references.
2. Measure clipping and ringing near step edges, edge transfer MTF, RMSE/PSNR and SSIM. Measure chroma against proper YUV ground truth.
3. Check GPU frame time at 23.976, 24, 50 and 59.94 fps, dropped frames and memory overhead on Shield Tegra X1+.
4. Blind, matched-output visual comparisons versus madVR and Shield AI. No claim of surpassing madVR without data.
5. Preserve current native 4K, HDR10, Dolby Vision and audio passthrough path exactly as is.

## Using the fragment shader in a separate OpenGL ES test harness
Compile `low_ringing_6tap.frag` as a GLSL ES 3.0 fragment shader with a fullscreen vertex shader supplying `vTexCoord`. Render one pass using `uAxis=(1,0)`, input 1920x1080 and output 3840x1080. Render a second pass with `uAxis=(0,1)`, input 3840x1080 and output 3840x2160. Allocate floating-point intermediate output where supported to avoid 8-bit intermediate clipping; compare both 8-bit SDR and high-precision paths. The clamp controls are experiments, not recommended defaults.

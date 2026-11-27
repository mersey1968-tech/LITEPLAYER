# RC1 binary audit — 2026-11-27

Inspected actual APK with Python ZIP reader, readelf and strings. This is a technical inventory, not legal clearance.

## Identity
- APK: Reflite-RC1.apk, 18,518,100 bytes.
- SHA-256: 02ec50481cc8655f845a8bdff0c69e9b87e42270d7d742830e51ee1418d07884.
- Byte-identical to Reflite-1080-AFRFirst.apk extracted from original CI artifact 15224743064.
- CI archive SHA-256: aa219467989f68c1dc12f7498638dd71a07b3a8f13b96e48f8d9e92b518cad16.
- APK ZIP integrity passed.

## Native libraries
Both arm64-v8a and armeabi-v7a contain libavcodec.so, libavutil.so, libswresample.so, libswscale.so and libmedia3ext.so. All inspected ELF LOAD segments have 0x4000 (16 KiB) alignment; this alone does not certify Android 16 KiB compatibility.
FFmpeg binaries identify version 6.0 and LGPL version 3 or later. Embedded configuration includes --enable-version3, --enable-shared, --disable-static, --enable-libvpx, --enable-mbedtls and --disable-asm; no --enable-gpl or --enable-nonfree found in the recorded configuration. Enabled decoders: vorbis, opus, flac, alac, pcm_mulaw, pcm_alaw, mp3, amrnb, amrwb, aac, ac3, eac3, dca, mlp, truehd, h264, hevc, mpeg2video, mpegvideo, libvpx_vp8, libvpx_vp9. NDK path identifies 25.2.9519653. libvpx static build configuration also present. Exact libvpx and mbedTLS revisions and actual linked code need verification.
libmedia3ext links the four FFmpeg libraries. NextLib upstream and exact declared Maven version 1.7.1-0.9.0 identify GPL-3.0; FFmpeg's LGPL status does not remove this separate obligation.

## Java/Kotlin and assets
DEX descriptors contain jcifs, Bouncy Castle, SLF4J, NextLib, AndroidX Media3 and Kotlin coroutines. Metadata confirms AndroidX Activity 1.9.3 and coroutines 1.6.4. Resolve full runtime dependency versions, copyrights and license terms via Gradle. Both FSRCNNX shader assets present: 16-channel 246363 bytes; 8-channel 71296 bytes. APK contains an AndroidX annotation license text but no comprehensive license/notice bundle. No separate proprietary Dolby/DTS library identified by filename; decoder code and patent obligations still require review.

## Outstanding
- Match exact historical NextLib artifact and native build source, including upstream modifications and linked dependency source.
- Verify original app and IEC audio code provenance and rights; exact shader provenance and preferred form for modifications.
- Assemble license texts, copyright notices and corresponding source/access and applicable relinking instructions before distribution.
- Review codec patents separately, including actual bundled software decoders.
- Do not publish draft until remaining checks resolved.

References: https://ffmpeg.org/legal.html ; https://github.com/anilbeesetti/nextlib ; https://mvnrepository.com/artifact/io.github.anilbeesetti/nextlib-media3ext/1.7.1-0.9.0 ; https://www.gnu.org/licenses/gpl-faq.html

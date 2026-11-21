# LitePlayer

**Picture First. Sound Uncompromised.**

LitePlayer is a free Android TV video player built for home-theater enthusiasts, with an emphasis on picture quality, audio fidelity, and display timing.

## Features

- **4K playback** on compatible Android TV devices; development testing focused on NVIDIA Shield TV.
- **Automatic frame-rate matching (AFR)** to request a display refresh rate suited to the video on supported devices.
- **HDR and Dolby Vision format handling**, subject to device, decoder, profile and display compatibility.
- **HDMI audio passthrough** for supported compressed audio formats with compatible hardware and connections; unsupported formats may decode to PCM.
- **SMB network playback** with increased read-ahead and playback buffering.
- Local files and network URLs, audio track selection, subtitles and TV-remote-friendly controls.

## Status

**Preparing the first public release.** The 4K SMB playback improvements were user-tested on an NVIDIA Shield TV. Broader device, HDR, Dolby Vision, codec and receiver compatibility is not yet verified.

The tested code is preserved on branch `liteplayer-stable-buffered-4k-2026-11-21`. Public-release materials are being prepared separately. Do not mistake debug builds for signed production releases.

## Installation

Once the public package is ready, download the signed APK from [GitHub Releases](https://github.com/mersey1968-tech/LITEPLAYER/releases). Follow the release's installation and verification instructions.

## Third-party code and distribution licensing

This project references AndroidX Media3 and third-party multimedia code. Some IEC audio code is attributed to FFmpeg/LGPL and Jellyfin-related work (see `source-review/IEC_SOURCE_ATTRIBUTION.txt`). A complete audit of source distribution, notices, library licenses and signing is required before a public binary release. This README does not declare the project to be open source or fully cleared for redistribution.

## Feedback

Report device/firmware, video profile/container, audio equipment, and steps to reproduce using GitHub Issues. Do not upload copyrighted media.

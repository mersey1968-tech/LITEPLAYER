# Reflite

Reference-quality Android TV media player with motion-compensated temporal video reconstruction, developed and tested primarily on NVIDIA Shield Pro and Sony Bravia 9.

## Current status

RC1 is an internal release candidate, based on the tested AFR-first startup build. Public binary distribution is not yet open: third-party license compliance, source provenance and codec patent review remain outstanding.

## Features

- Separate temporal reconstruction paths for 720p and 1080p SDR content.
- Automatic frame-rate matching and native HDR10/Dolby Vision playback on compatible devices.
- Dolby TrueHD/Atmos and DTS-HD MA bitstream passthrough on supported hardware.
- SMB browsing and external-player integration.
- Minimal playback interface.

## Known limitations

A brief startup hitch can occur before the automatic six-frame synchronization seek on 1080p. Performance on other Android TV devices is not guaranteed. No claim of full Dolby Vision Profile 7 FEL reconstruction, official Dolby/DTS certification, or objective superiority over other scalers is made.

## Availability

The intended release is free, without ads or subscriptions. Public APK downloads and source distribution instructions will be added only after compliance review. Please do not redistribute internal test builds.

[Third-party credits and compliance review](REFLITE-NOTICES.md) · [Release checklist](REFLITE-RELEASE.md)

Feedback from experienced home theater users is welcome through GitHub Issues. Please include device, source resolution/frame rate, audio format, and observed behavior; do not share private media URLs or credentials.

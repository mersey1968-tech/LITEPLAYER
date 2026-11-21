# Seamless next-episode integration (experimental)

## Status
LitePlayer now accepts optional `next_episode_url` alongside the current Android ACTION_VIEW stream URL. It inserts both media items into the SAME ExoPlayer playlist to avoid leaving the player between episodes. The existing subtitle, audio, HDR, and AFR code paths are unchanged.

**This does not yet enable next-episode autoplay from stock Plezy.** The current Plezy Android `ExternalPlayerChannel.buildIntent()` supplies only the current stream, playback position, and subtitle tracks, not a next-episode URL. No code change inside LitePlayer can manufacture the authenticated next Plex stream.

## Required Plezy-side change
1. Before external launch, use Plezy's episode-navigation service / playback queue to resolve the next Plex episode.
2. Resolve its direct-play authenticated stream using the same server client, media index, and server selection as the current video.
3. In `android/app/src/main/kotlin/com/edde746/plezy/ExternalPlayerChannel.kt`, add a nullable `nextEpisodeUrl` argument to `buildIntent()` and send `putExtra("next_episode_url", nextEpisodeUrl)` when the next URL is present.
4. Update `lib/services/external_player_service.dart` MethodChannel call and native handler to pass that value through.
5. **Important:** Plezy currently expects only one activity result when external playback returns. For a queued pair, implement *per-episode completion reporting* from LitePlayer to Plezy before considering the integration production ready. Otherwise Plex may not mark the first item watched.
6. Decide how to continue past the second episode, e.g. a queue refresh handshake. Two URLs alone do not implement an unlimited continuous series queue.

## Technical caveats
- The prototype holds the upcoming URL in process only; do not persist expiring Plex tokens.
- Even an in-player transition may briefly blank the display if content changes frame rate or HDR mode, because AFR must remain enabled.
- This branch is a proof of the LitePlayer-side mechanism, not a verified Plezy integration. Preserve the `liteplayer-stable-2026-11-21` branch and its successful build.
- Do not replace the stable installation with this prototype just to test Plezy's existing auto-next behavior; stock Plezy doesn't send the required extra.

# Changelog

## 2026-04-26

### New Discovery Commands

Added four new voice commands using Plex API sort and filter parameters:

- **Play recently played** (`PlayRecentlyPlayedIntent`) — queries `lastViewedAt:desc` for the top 100 played tracks and shuffles them. Falls back to a random 100-track sample from the full library if no play history exists. "Ask Plex to play music" with no qualifier routes here.
- **Play most played** (`PlayMostPlayedIntent`) — queries `viewCount:desc` for the top 100 tracks and shuffles them.
- **Play by genre** (`PlayGenreIntent`) — looks up the exact genre title from Plex's genre list (case-insensitive, partial match), then fetches and shuffles up to 100 tracks. "Ask Plex to play some Rock."
- **Play recently added** (`PlayRecentlyAddedIntent`) — fetches the 100 most recently added tracks sorted by `addedAt:desc`, filters to past 30 days; if empty, expands to past year; if still empty, responds that nothing new was found.

Also added `GENRE_TYPE` custom slot type to the Alexa interaction model with 22 common genres and synonyms.

---

## Development History

This project was built collaboratively with Claude AI (Anthropic) as a replacement
for the official Plex Alexa skill after Plex announced its discontinuation.

### Core Features Built
- Flask + ask-sdk skill endpoint with proper Alexa AudioPlayer integration
- Plex API client with search for artists, albums, tracks, playlists
- Per-device in-memory queue manager for independent multi-device playback
- Decade-based search using Plex album decade filter
- Album art and metadata for Echo Show devices
- Fallback logic for tracks returned as album ratingKeys by Plex search
- Full track metadata fetch when search returns lightweight results

### Infrastructure
- Docker container with gunicorn (single worker, 4 threads for shared queue state)
- Apache reverse proxy with path-based routing and HTTP method restrictions
- Docker secrets for Plex token
- iptables auto-heal script for Docker FORWARD chain bug on Linux

### Known Issues Fixed
- ask-sdk-webservice-support API compatibility (WebserviceSkillHandler vs SkillAdapter)
- Plex search returns SearchResult[].Metadata not Metadata[] directly
- Queue split-brain with multiple gunicorn workers
- ClearQueue directive needed before REPLACE_ALL to flush Alexa's buffer
- track_to_info missing for decade search branch
- Plex token read from Docker secrets file path
- AudioPlayer interface must be enabled in Alexa developer console

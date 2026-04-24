# Changelog

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

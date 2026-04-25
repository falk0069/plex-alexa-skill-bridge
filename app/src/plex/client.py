"""
Plex API client for searching and streaming music.
"""
import os
import random
import logging
import requests
from urllib.parse import urljoin, quote

logger = logging.getLogger(__name__)

PLEX_HOST = os.environ.get('PLEX_HOST', 'http://YOUR_PLEX_IP:32400')
# Accept either bare FQDN or https://FQDN — normalize to bare FQDN at load time.
# https:// is always prepended when building public URLs.
_raw_public_host = os.environ.get('PLEX_PUBLIC_HOST', '')
PLEX_PUBLIC_HOST = _raw_public_host.removeprefix('https://').removeprefix('http://').rstrip('/')

def _read_secret(env_var, default=''):
    """Read env var value — if it looks like a file path, read the file contents instead."""
    val = os.environ.get(env_var, default)
    if val and val.startswith('/'):
        try:
            with open(val, 'r') as f:
                return f.read().strip()
        except Exception:
            pass
    return val.strip()

PLEX_TOKEN = _read_secret('PLEX_TOKEN')

SESSION = requests.Session()
SESSION.headers.update({'Accept': 'application/json'})


def _params(**kwargs):
    """Build common Plex API query params."""
    p = {'X-Plex-Token': PLEX_TOKEN}
    p.update(kwargs)
    return p


def _get(path, **kwargs):
    """Make a GET request to the Plex server."""
    url = PLEX_HOST.rstrip('/') + path
    try:
        resp = SESSION.get(url, params=_params(**kwargs), timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Plex API error for {path}: {e}")
        return None



def search_tracks(query):
    """Search for tracks matching the query. Returns list of track dicts."""
    data = _get('/library/search', query=query, type=10, limit=50)
    if not data:
        logger.warning(f"search_tracks: no data returned for query={query!r}")
        return []
    mc = data.get('MediaContainer', {})
    # Plex returns SearchResult[].Metadata, not Metadata[] directly
    search_results = mc.get('SearchResult', []) or []
    results = [sr['Metadata'] for sr in search_results if 'Metadata' in sr]
    logger.info(f"search_tracks: query={query!r} results={len(results)} first={results[0].get('title') if results else None}")
    return results


def search_artists(query):
    """Search for artists matching the query. Returns list of artist dicts."""
    data = _get('/library/search', query=query, type=8, limit=20)
    if not data:
        logger.warning(f"search_artists: no data returned for query={query!r}")
        return []
    mc = data.get('MediaContainer', {})
    search_results = mc.get('SearchResult', []) or []
    results = [sr['Metadata'] for sr in search_results if 'Metadata' in sr]
    logger.info(f"search_artists: query={query!r} results={len(results)} first={results[0].get('title') if results else None}")
    return results


def search_albums(query):
    """Search for albums matching the query. Returns list of album dicts."""
    data = _get('/library/search', query=query, type=9, limit=20)
    if not data:
        logger.warning(f"search_albums: no data returned for query={query!r}")
        return []
    mc = data.get('MediaContainer', {})
    search_results = mc.get('SearchResult', []) or []
    results = [sr['Metadata'] for sr in search_results if 'Metadata' in sr]
    logger.info(f"search_albums: query={query!r} results={len(results)} first={results[0].get('title') if results else None}")
    return results


def search_playlists(query):
    """Search for playlists matching the query. Returns list of playlist dicts."""
    data = _get('/playlists', playlistType='audio')
    if not data:
        return []
    playlists = data.get('MediaContainer', {}).get('Metadata', []) or []
    query_lower = query.lower()
    # Filter by name similarity
    matches = [p for p in playlists if query_lower in p.get('title', '').lower()]
    return matches


def get_artist_tracks(artist_rating_key):
    """Get all tracks for an artist, shuffled. Falls back through albums if allLeaves fails."""
    data = _get(f'/library/metadata/{artist_rating_key}/allLeaves')
    if data:
        mc = data.get('MediaContainer', {})
        tracks = mc.get('Metadata', []) or []
        if tracks:
            logger.info(f"get_artist_tracks: ratingKey={artist_rating_key} found={len(tracks)} via allLeaves")
            random.shuffle(tracks)
            return tracks

    # Fall back: get albums then get tracks from each album
    logger.info(f"get_artist_tracks: falling back to album traversal for ratingKey={artist_rating_key}")
    albums_data = _get(f'/library/metadata/{artist_rating_key}/children')
    if not albums_data:
        return []
    albums = albums_data.get('MediaContainer', {}).get('Metadata', []) or []
    all_tracks = []
    for album in albums:
        album_key = album.get('ratingKey')
        if not album_key:
            continue
        track_data = _get(f'/library/metadata/{album_key}/children')
        if track_data:
            tracks = track_data.get('MediaContainer', {}).get('Metadata', []) or []
            all_tracks.extend(tracks)
    logger.info(f"get_artist_tracks: album traversal found {len(all_tracks)} tracks")
    random.shuffle(all_tracks)
    return all_tracks


def get_album_tracks(album_rating_key):
    """Get all tracks for an album in order."""
    data = _get(f'/library/metadata/{album_rating_key}/children')
    if not data:
        return []
    return data.get('MediaContainer', {}).get('Metadata', []) or []


def get_playlist_tracks(playlist_rating_key):
    """Get all tracks in a playlist."""
    data = _get(f'/playlists/{playlist_rating_key}/items')
    if not data:
        return []
    tracks = data.get('MediaContainer', {}).get('Metadata', []) or []
    return tracks


def get_stream_url(track, public=True):
    """
    Build a stream URL for a track.
    If public=True, use PLEX_PUBLIC_HOST for Alexa-accessible HTTPS URL.
    """
    try:
        media_list = track.get('Media') or []
        if not media_list:
            logger.error(f"get_stream_url: no Media on track {track.get('title')!r}")
            return None
        media = media_list[0]

        # Media can be a dict or an object
        if hasattr(media, 'part'):
            parts = media.part or []
            part = parts[0] if parts else None
            key = part.key if part and hasattr(part, 'key') else None
        else:
            parts = media.get('Part') or []
            part = parts[0] if parts else None
            key = part.get('key') if part else None

        if not key:
            logger.error(f"get_stream_url: no Part key on track {track.get('title')!r} media={media}")
            return None

        token_param = f"?X-Plex-Token={PLEX_TOKEN}"

        if public and PLEX_PUBLIC_HOST:
            return f"https://{PLEX_PUBLIC_HOST}{key}{token_param}"
        else:
            base = PLEX_HOST.rstrip('/')
            return f"{base}{key}{token_param}"
    except Exception as e:
        logger.error(f"get_stream_url error for {track.get('title')!r}: {e}", exc_info=True)
        return None


def get_thumb_url(track, public=True):
    """Build a public thumbnail URL for a track."""
    thumb = track.get('thumb') or track.get('parentThumb') or track.get('grandparentThumb')
    if not thumb:
        return None
    token_param = f"?X-Plex-Token={PLEX_TOKEN}"
    if public and PLEX_PUBLIC_HOST:
        return f"https://{PLEX_PUBLIC_HOST}{thumb}{token_param}"
    base = PLEX_HOST.rstrip('/')
    return f"{base}{thumb}{token_param}"


def track_to_info(track):
    """Convert a Plex track metadata dict to a simple info dict."""
    # If Media is missing, fetch full track details using ratingKey
    if not track.get('Media') and track.get('ratingKey'):
        data = _get(f'/library/metadata/{track["ratingKey"]}')
        if data:
            items = data.get('MediaContainer', {}).get('Metadata', [])
            if items:
                fetched = items[0]
                # If fetched item is an album, get its first track instead
                if fetched.get('type') == 'album':
                    logger.info(f"track_to_info: {track.get('title')!r} is an album, fetching tracks")
                    children = _get(f'/library/metadata/{fetched["ratingKey"]}/children')
                    if children:
                        tracks = children.get('MediaContainer', {}).get('Metadata', []) or []
                        if tracks:
                            track = tracks[0]
                            logger.info(f"track_to_info: resolved to track {track.get('title')!r}")
                else:
                    track = fetched
                    logger.info(f"track_to_info: fetched full metadata for {track.get('title')!r}")

    return {
        'title': track.get('title', 'Unknown'),
        'artist': track.get('grandparentTitle', track.get('originalTitle', 'Unknown')),
        'album': track.get('parentTitle', 'Unknown'),
        'stream_url': get_stream_url(track, public=True),
        'thumb_url': get_thumb_url(track, public=True),
        'rating_key': track.get('ratingKey'),
        'duration': track.get('duration', 0),
    }



def search_tracks_by_decade(decade):
    """Search for tracks from a given decade via album decade filter."""
    import re
    decade_str = str(decade).lower().strip()

    word_map = {
        'fifties': 1950, 'the fifties': 1950,
        'sixties': 1960, 'the sixties': 1960,
        'seventies': 1970, 'the seventies': 1970,
        'eighties': 1980, 'the eighties': 1980,
        'nineties': 1990, 'the nineties': 1990,
        'two thousands': 2000, 'the two thousands': 2000,
        'twenty tens': 2010, 'the twenty tens': 2010,
        'twenty twenties': 2020, 'the twenty twenties': 2020,
    }

    if decade_str in word_map:
        start_year = word_map[decade_str]
    else:
        digits = re.sub(r'[^0-9]', '', decade_str)
        if not digits:
            logger.error(f"Could not parse decade: {decade!r}")
            return []
        try:
            start_year = int(digits)
            if start_year < 100:
                start_year += 1900
        except ValueError:
            logger.error(f"Could not parse decade digits: {digits!r}")
            return []

    logger.info(f"Decade parsed: {decade!r} -> start_year={start_year}")

    section_key = _get_music_section_key()
    if not section_key:
        logger.error("No music section found")
        return []

    # Plex 'decade' filter on albums uses the decade start year (e.g. 1990 for 90s)
    data = _get(f'/library/sections/{section_key}/all', type=9, decade=start_year)
    if not data:
        return []
    albums = data.get('MediaContainer', {}).get('Metadata', []) or []
    logger.info(f"Decade {start_year}: found {len(albums)} albums, fetching tracks...")

    # Shuffle albums then collect tracks (cap at 30 albums to avoid timeout)
    random.shuffle(albums)
    all_tracks = []
    for album in albums[:30]:
        album_key = album.get('ratingKey')
        if not album_key:
            continue
        track_data = _get(f'/library/metadata/{album_key}/children')
        if track_data:
            tracks = track_data.get('MediaContainer', {}).get('Metadata', []) or []
            all_tracks.extend(tracks)

    logger.info(f"Decade {start_year}: collected {len(all_tracks)} tracks total")
    random.shuffle(all_tracks)
    return all_tracks
def _get_music_section_key():
    """Get the key for the first music library section."""
    data = _get('/library/sections')
    if not data:
        return None
    for section in data.get('MediaContainer', {}).get('Directory', []):
        if section.get('type') == 'artist':
            return section.get('key')
    return None

def resolve_play_request(query_type, query):
    """
    Main entry point: given a type and query string, return a list of track info dicts.
    query_type: 'song', 'artist', 'album', 'playlist'
    Returns (tracks, description) tuple.
    """
    query = query.strip()
    logger.info(f"Resolving play request: type={query_type}, query={query!r}")

    if query_type == 'song':
        results = search_tracks(query)
        if not results:
            return [], f"I couldn't find a song called {query}"
        # Pick best match (first result = closest match from Plex)
        track = results[0]
        return [track_to_info(track)], f"Playing {track.get('title')} by {track.get('grandparentTitle', 'Unknown')}"

    elif query_type == 'artist':
        results = search_artists(query)
        if not results:
            return [], f"I couldn't find an artist called {query}"
        artist = results[0]
        artist_name = artist.get('title', query)
        tracks = get_artist_tracks(artist.get('ratingKey'))
        if not tracks:
            # Last resort: search tracks by artist name
            logger.info(f"Artist track lookup failed, falling back to track search for {artist_name!r}")
            track_results = search_tracks(artist_name)
            tracks_filtered = [t for t in track_results
                               if query.lower() in (t.get('grandparentTitle') or '').lower()]
            if not tracks_filtered:
                tracks_filtered = track_results
            if not tracks_filtered:
                return [], f"I couldn't find any songs for {artist_name}"
            random.shuffle(tracks_filtered)
            track_infos = [track_to_info(t) for t in tracks_filtered]
            return track_infos, f"Shuffling {artist_name}"
        track_infos = [track_to_info(t) for t in tracks]
        return track_infos, f"Shuffling {artist_name}"

    elif query_type == 'album':
        results = search_albums(query)
        if not results:
            return [], f"I couldn't find an album called {query}"
        album = results[0]
        tracks = get_album_tracks(album.get('ratingKey'))
        if not tracks:
            return [], f"I couldn't find any tracks on {album.get('title')}"
        track_infos = [track_to_info(t) for t in tracks]
        return track_infos, f"Playing {album.get('title')} by {album.get('parentTitle', 'Unknown')}"

    elif query_type == 'playlist':
        results = search_playlists(query)
        if not results:
            return [], f"I couldn't find a playlist called {query}"
        playlist = results[0]
        tracks = get_playlist_tracks(playlist.get('ratingKey'))
        if not tracks:
            return [], f"The playlist {playlist.get('title')} appears to be empty"
        track_infos = [track_to_info(t) for t in tracks]
        return track_infos, f"Playing playlist {playlist.get('title')}"

    elif query_type == 'decade':
        tracks = search_tracks_by_decade(query)
        if not tracks:
            return [], f"I couldn't find any songs from the {query}"
        track_infos = [track_to_info(t) for t in tracks]
        return track_infos, f"Shuffling music from the {query}"

    return [], "I didn't understand what you wanted to play"

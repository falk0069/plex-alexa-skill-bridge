"""
In-memory queue manager for multi-track Alexa playback.
Stores the current queue per Alexa device (user ID).
"""
import logging
import threading

logger = logging.getLogger(__name__)

# Global queue store: { user_id: { 'tracks': [...], 'index': int } }
_queues = {}
_lock = threading.Lock()


def set_queue(user_id, tracks, index=0):
    """Set the queue for a user."""
    with _lock:
        _queues[user_id] = {
            'tracks': tracks,
            'index': index,
            'offset_ms': 0,
        }
    logger.info(f"Queue set for {user_id}: {len(tracks)} tracks, starting at {index}")


def get_current_track(user_id):
    """Get the current track info dict for a user, or None."""
    with _lock:
        q = _queues.get(user_id)
        if not q:
            return None
        tracks = q['tracks']
        index = q['index']
        if index >= len(tracks):
            return None
        return tracks[index]


def get_next_track(user_id):
    """Peek at the next track without advancing the index."""
    with _lock:
        q = _queues.get(user_id)
        if not q:
            return None
        tracks = q['tracks']
        index = q['index'] + 1
        if index >= len(tracks):
            return None
        return tracks[index]


def advance_queue(user_id):
    """Advance to the next track. Returns the new current track or None if end."""
    with _lock:
        q = _queues.get(user_id)
        if not q:
            return None
        q['index'] += 1
        q['offset_ms'] = 0
        tracks = q['tracks']
        index = q['index']
        if index >= len(tracks):
            logger.info(f"Queue exhausted for {user_id}")
            return None
        return tracks[index]


def clear_queue(user_id):
    """Clear the queue for a user."""
    with _lock:
        _queues.pop(user_id, None)


def get_queue_length(user_id):
    """Return total number of tracks in queue."""
    with _lock:
        q = _queues.get(user_id)
        if not q:
            return 0
        return len(q['tracks'])


def get_queue_index(user_id):
    """Return current index in queue."""
    with _lock:
        q = _queues.get(user_id)
        if not q:
            return 0
        return q['index']


def get_track_at_index(user_id, index):
    """Return the track at an explicit index, or None if out of range."""
    with _lock:
        q = _queues.get(user_id)
        if not q:
            return None
        tracks = q['tracks']
        if index < 0 or index >= len(tracks):
            return None
        return tracks[index]


def set_offset(user_id, offset_ms):
    """Save the playback position for the current track."""
    with _lock:
        q = _queues.get(user_id)
        if q:
            q['offset_ms'] = offset_ms


def get_offset(user_id):
    """Return the saved playback position, or 0."""
    with _lock:
        q = _queues.get(user_id)
        return q.get('offset_ms', 0) if q else 0

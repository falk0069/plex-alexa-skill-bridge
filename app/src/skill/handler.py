"""
Alexa skill handler for Plex music playback.
Handles PlayMusic intent, AudioPlayer events, and playback controls.
"""
import logging
import json
from ask_sdk_core.skill_builder import SkillBuilder
from ask_sdk_core.dispatch_components import AbstractRequestHandler, AbstractExceptionHandler
from ask_sdk_core.utils import is_intent_name, is_request_type
from ask_sdk_model.ui import StandardCard, Image
from ask_sdk_model.interfaces.audioplayer import (
    PlayDirective, PlayBehavior, AudioItem, Stream, AudioItemMetadata,
    StopDirective, ClearQueueDirective, ClearBehavior
)

from plex.client import resolve_play_request
from skill.queue import (
    set_queue, get_current_track,
    advance_queue, clear_queue, get_queue_length, get_queue_index,
    get_track_at_index, set_offset, get_offset,
)

logger = logging.getLogger(__name__)
sb = SkillBuilder()

TOKEN_PREFIX = "plex-track-"


def _user_id(handler_input):
    return handler_input.request_envelope.session.user.user_id if handler_input.request_envelope.session else \
        handler_input.request_envelope.context.system.user.user_id


def _build_play_directive(track, behavior=PlayBehavior.REPLACE_ALL, previous_token=None, index=0, offset_ms=0):
    """Build an Alexa AudioPlayer Play directive from a track info dict."""
    from ask_sdk_model.interfaces.display.image import Image as DisplayImage
    from ask_sdk_model.interfaces.display.image_instance import ImageInstance

    stream_url = track.get('stream_url')
    # Encode index in token so NearlyFinished can find the right next track
    # even if in-memory queue state drifts.
    token = f"{TOKEN_PREFIX}{index}-{track.get('rating_key', 'unknown')}"

    logger.info(f"Building play directive: artist={track.get('artist')!r} title={track.get('title')!r} url={stream_url!r}")

    if not stream_url:
        logger.error("No stream_url on track — cannot build directive")
        return None

    # Build album art image for Echo Show display
    thumb_url = track.get('thumb_url')
    if thumb_url:
        art_image = DisplayImage(
            content_description=track.get('title', ''),
            sources=[
                ImageInstance(url=thumb_url, size='MEDIUM'),
                ImageInstance(url=thumb_url, size='LARGE'),
            ]
        )
        bg_image = DisplayImage(
            content_description=track.get('title', ''),
            sources=[
                ImageInstance(url=thumb_url, size='X_LARGE'),
            ]
        )
    else:
        art_image = None
        bg_image = None

    metadata = AudioItemMetadata(
        title=track.get('title', 'Unknown'),
        subtitle=f"{track.get('artist', '')} — {track.get('album', '')}",
        art=art_image,
        background_image=bg_image,
    )

    return PlayDirective(
        play_behavior=behavior,
        audio_item=AudioItem(
            stream=Stream(
                token=token,
                url=stream_url,
                offset_in_milliseconds=offset_ms,
                expected_previous_token=previous_token,
            ),
            metadata=metadata,
        )
    )


def _speak_and_play(handler_input, tracks, description):
    """Set queue, speak description, and issue play directive for first track."""
    user_id = _user_id(handler_input)
    set_queue(user_id, tracks)
    track = tracks[0]
    directive = _build_play_directive(track, PlayBehavior.REPLACE_ALL)
    count = len(tracks)
    suffix = f" {count} songs queued." if count > 1 else "."

    if directive is None:
        logger.error(f"Failed to build play directive for track: {track}")
        return (
            handler_input.response_builder
            .speak("Sorry, I couldn't build a stream URL for that track.")
            .response
        )

    logger.info(f"Returning play response: {description + suffix}")
    # Clear Alexa's existing queue before starting new playback
    # This prevents previously enqueued tracks from playing after REPLACE_ALL
    return (
        handler_input.response_builder
        .speak(description + suffix)
        .add_directive(ClearQueueDirective(clear_behavior=ClearBehavior.CLEAR_ALL))
        .add_directive(directive)
        .response
    )


# ── Intent Handlers ────────────────────────────────────────────────────────────

class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input):
        return (
            handler_input.response_builder
            .speak("Welcome to Plex. You can say: play a song, play an artist, play an album, or play a playlist.")
            .ask("What would you like to play?")
            .response
        )


class PlayMusicIntentHandler(AbstractRequestHandler):
    """Handles: play [song/artist/album/playlist] [name]"""

    def can_handle(self, handler_input):
        try:
            return is_intent_name("PlayMusicIntent")(handler_input)
        except Exception as e:
            logger.error(f"PlayMusicIntent can_handle error: {e}")
            return False

    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}

        query_type = None
        query = None

        # Check each slot
        song_slot = slots.get('song')
        artist_slot = slots.get('artist')
        album_slot = slots.get('album')
        playlist_slot = slots.get('playlist')

        if song_slot and song_slot.value:
            query_type = 'song'
            query = song_slot.value
        elif artist_slot and artist_slot.value:
            query_type = 'artist'
            query = artist_slot.value
        elif album_slot and album_slot.value:
            query_type = 'album'
            query = album_slot.value
        elif playlist_slot and playlist_slot.value:
            query_type = 'playlist'
            query = playlist_slot.value

        if not query_type or not query:
            # No slot filled — treat as "play music" → recently played (falls back to random)
            tracks, description = resolve_play_request('recently_played', '')
            if not tracks:
                return (
                    handler_input.response_builder
                    .speak(description)
                    .ask("What would you like to play?")
                    .response
                )
            return _speak_and_play(handler_input, tracks, description)

        tracks, description = resolve_play_request(query_type, query)

        if not tracks:
            return (
                handler_input.response_builder
                .speak(description + ". Please try again.")
                .ask("What would you like to play?")
                .response
            )

        return _speak_and_play(handler_input, tracks, description)


class ShuffleArtistIntentHandler(AbstractRequestHandler):
    """Handles: shuffle [artist]"""

    def can_handle(self, handler_input):
        return is_intent_name("ShuffleArtistIntent")(handler_input)

    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}
        artist_slot = slots.get('artist')
        query = artist_slot.value if artist_slot else None

        if not query:
            return (
                handler_input.response_builder
                .speak("Which artist would you like to shuffle?")
                .ask("Which artist?")
                .response
            )

        tracks, description = resolve_play_request('artist', query)
        if not tracks:
            return (
                handler_input.response_builder
                .speak(description)
                .ask("What would you like to play?")
                .response
            )

        return _speak_and_play(handler_input, tracks, description)




class PlayDecadeIntentHandler(AbstractRequestHandler):
    """Handles: play music from the [decade]s"""

    def can_handle(self, handler_input):
        try:
            return is_intent_name("PlayDecadeIntent")(handler_input)
        except Exception:
            return False

    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}
        decade_slot = slots.get('decade')
        query = decade_slot.value if decade_slot else None

        if not query:
            return (
                handler_input.response_builder
                .speak("Which decade would you like to hear? Try saying the 1990s.")
                .ask("Which decade?")
                .response
            )

        from plex.client import resolve_play_request
        tracks, description = resolve_play_request('decade', query)
        if not tracks:
            return (
                handler_input.response_builder
                .speak(description)
                .ask("What would you like to play?")
                .response
            )

        return _speak_and_play(handler_input, tracks, description)

class PlayRecentlyPlayedIntentHandler(AbstractRequestHandler):
    """Handles: play music / play recently played music"""

    def can_handle(self, handler_input):
        return is_intent_name("PlayRecentlyPlayedIntent")(handler_input)

    def handle(self, handler_input):
        tracks, description = resolve_play_request('recently_played', '')
        if not tracks:
            return (
                handler_input.response_builder
                .speak(description)
                .ask("What would you like to play?")
                .response
            )
        return _speak_and_play(handler_input, tracks, description)


class PlayMostPlayedIntentHandler(AbstractRequestHandler):
    """Handles: play my most played music"""

    def can_handle(self, handler_input):
        return is_intent_name("PlayMostPlayedIntent")(handler_input)

    def handle(self, handler_input):
        tracks, description = resolve_play_request('most_played', '')
        if not tracks:
            return (
                handler_input.response_builder
                .speak(description)
                .ask("What would you like to play?")
                .response
            )
        return _speak_and_play(handler_input, tracks, description)


class PlayGenreIntentHandler(AbstractRequestHandler):
    """Handles: play the genre [genre]"""

    def can_handle(self, handler_input):
        return is_intent_name("PlayGenreIntent")(handler_input)

    def handle(self, handler_input):
        slots = handler_input.request_envelope.request.intent.slots or {}
        genre_slot = slots.get('genre')
        query = genre_slot.value if genre_slot else None

        if not query:
            return (
                handler_input.response_builder
                .speak("Which genre would you like to hear?")
                .ask("Which genre?")
                .response
            )

        tracks, description = resolve_play_request('genre', query)
        if not tracks:
            return (
                handler_input.response_builder
                .speak(description + ". Please try again.")
                .ask("What would you like to play?")
                .response
            )
        return _speak_and_play(handler_input, tracks, description)


class PlayRecentlyAddedIntentHandler(AbstractRequestHandler):
    """Handles: play recently added music"""

    def can_handle(self, handler_input):
        return is_intent_name("PlayRecentlyAddedIntent")(handler_input)

    def handle(self, handler_input):
        tracks, description = resolve_play_request('recently_added', '')
        if not tracks:
            return (
                handler_input.response_builder
                .speak(description)
                .response
            )
        return _speak_and_play(handler_input, tracks, description)


# ── AudioPlayer Event Handlers ─────────────────────────────────────────────────

class PlaybackNearlyFinishedHandler(AbstractRequestHandler):
    """Enqueue the next track when current track is nearly done."""

    def can_handle(self, handler_input):
        return is_request_type("AudioPlayer.PlaybackNearlyFinished")(handler_input)

    def handle(self, handler_input):
        user_id = _user_id(handler_input)
        current_token = handler_input.request_envelope.request.token

        # Decode the playing index from the token (format: plex-track-{index}-{key})
        try:
            next_index = int(current_token[len(TOKEN_PREFIX):].split('-')[0]) + 1
        except (ValueError, IndexError):
            next_index = get_queue_index(user_id) + 1

        next_track = get_track_at_index(user_id, next_index)

        if next_track and next_track.get('stream_url'):
            directive = _build_play_directive(
                next_track,
                behavior=PlayBehavior.ENQUEUE,
                previous_token=current_token,
                index=next_index,
            )
            return (
                handler_input.response_builder
                .add_directive(directive)
                .response
            )

        # No more tracks
        return handler_input.response_builder.response


class PlaybackFinishedHandler(AbstractRequestHandler):
    """Advance the queue index when a track finishes."""

    def can_handle(self, handler_input):
        return is_request_type("AudioPlayer.PlaybackFinished")(handler_input)

    def handle(self, handler_input):
        user_id = _user_id(handler_input)
        advance_queue(user_id)
        return handler_input.response_builder.response


class PlaybackStartedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("AudioPlayer.PlaybackStarted")(handler_input)

    def handle(self, handler_input):
        return handler_input.response_builder.response


class PlaybackStoppedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("AudioPlayer.PlaybackStopped")(handler_input)

    def handle(self, handler_input):
        user_id = _user_id(handler_input)
        offset_ms = getattr(handler_input.request_envelope.request, 'offset_in_milliseconds', 0) or 0
        set_offset(user_id, offset_ms)
        return handler_input.response_builder.response


class PlaybackFailedHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("AudioPlayer.PlaybackFailed")(handler_input)

    def handle(self, handler_input):
        logger.error(f"Playback failed: {handler_input.request_envelope.request}")
        user_id = _user_id(handler_input)
        advance_queue(user_id)
        return handler_input.response_builder.response


# ── Playback Control Handlers ──────────────────────────────────────────────────

class PauseIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.PauseIntent")(handler_input) or \
               is_intent_name("AMAZON.StopIntent")(handler_input)

    def handle(self, handler_input):
        return (
            handler_input.response_builder
            .add_directive(StopDirective())
            .response
        )


class ResumeIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.ResumeIntent")(handler_input)

    def handle(self, handler_input):
        user_id = _user_id(handler_input)
        track = get_current_track(user_id)
        if not track:
            return (
                handler_input.response_builder
                .speak("There's nothing to resume. Ask me to play something first.")
                .response
            )
        index = get_queue_index(user_id)
        offset_ms = get_offset(user_id)
        directive = _build_play_directive(track, PlayBehavior.REPLACE_ALL, index=index, offset_ms=offset_ms)
        return (
            handler_input.response_builder
            .add_directive(directive)
            .response
        )


class NextIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.NextIntent")(handler_input)

    def handle(self, handler_input):
        user_id = _user_id(handler_input)
        track = advance_queue(user_id)
        if not track:
            return (
                handler_input.response_builder
                .speak("That was the last song in the queue.")
                .add_directive(StopDirective())
                .response
            )
        index = get_queue_index(user_id)
        directive = _build_play_directive(track, PlayBehavior.REPLACE_ALL, index=index)
        return (
            handler_input.response_builder
            .add_directive(directive)
            .response
        )


class CancelIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.CancelIntent")(handler_input)

    def handle(self, handler_input):
        user_id = _user_id(handler_input)
        clear_queue(user_id)
        return (
            handler_input.response_builder
            .add_directive(StopDirective())
            .add_directive(ClearQueueDirective(clear_behavior=ClearBehavior.CLEAR_ALL))
            .response
        )


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input):
        return (
            handler_input.response_builder
            .speak(
                "You can say: play the song Africa, "
                "play the artist Toto, "
                "play the album Toto IV, "
                "or play the playlist Road Trip. "
                "You can also say next, pause, or resume."
            )
            .ask("What would you like to play?")
            .response
        )


class SystemExceptionHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_request_type("System.ExceptionEncountered")(handler_input)

    def handle(self, handler_input):
        logger.error(f"System exception: {handler_input.request_envelope.request}")
        return handler_input.response_builder.response


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input):
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input):
        return (
            handler_input.response_builder
            .speak("I'm not sure what you meant. Try saying: play the artist Fleetwood Mac.")
            .ask("What would you like to play?")
            .response
        )


class CatchAllRequestHandler(AbstractRequestHandler):
    """Catch-all handler for debugging — logs unhandled request types."""
    def can_handle(self, handler_input):
        return True

    def handle(self, handler_input):
        try:
            req = handler_input.request_envelope.request
            req_type = getattr(req, 'object_type', None) or type(req).__name__
            intent_name = getattr(req, 'intent', None)
            if intent_name:
                intent_name = getattr(intent_name, 'name', str(intent_name))
            logger.warning(f"CatchAll handler hit: request_type={req_type} intent={intent_name}")
        except Exception as e:
            logger.error(f"CatchAll handler error inspecting request: {e}")
        return (
            handler_input.response_builder
            .speak("Sorry, I didn't understand that request.")
            .response
        )


class GlobalExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input, exception):
        return True

    def handle(self, handler_input, exception):
        logger.error(f"Unhandled exception: {exception}", exc_info=True)
        return (
            handler_input.response_builder
            .speak("Sorry, something went wrong. Please try again.")
            .response
        )


# ── Register all handlers ──────────────────────────────────────────────────────

sb.add_request_handler(LaunchRequestHandler())
sb.add_request_handler(PlayMusicIntentHandler())
sb.add_request_handler(ShuffleArtistIntentHandler())
sb.add_request_handler(PlayDecadeIntentHandler())
sb.add_request_handler(PlayRecentlyPlayedIntentHandler())
sb.add_request_handler(PlayMostPlayedIntentHandler())
sb.add_request_handler(PlayGenreIntentHandler())
sb.add_request_handler(PlayRecentlyAddedIntentHandler())
sb.add_request_handler(PlaybackNearlyFinishedHandler())
sb.add_request_handler(PlaybackFinishedHandler())
sb.add_request_handler(PlaybackStartedHandler())
sb.add_request_handler(PlaybackStoppedHandler())
sb.add_request_handler(PlaybackFailedHandler())
sb.add_request_handler(PauseIntentHandler())
sb.add_request_handler(ResumeIntentHandler())
sb.add_request_handler(NextIntentHandler())
sb.add_request_handler(CancelIntentHandler())
sb.add_request_handler(HelpIntentHandler())
sb.add_request_handler(SystemExceptionHandler())
sb.add_request_handler(FallbackIntentHandler())
sb.add_request_handler(CatchAllRequestHandler())
sb.add_exception_handler(GlobalExceptionHandler())

skill_handler = sb.create()

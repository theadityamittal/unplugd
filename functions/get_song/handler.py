"""GET /songs/{songId} — retrieve a single song with optional presigned URLs."""

from __future__ import annotations

import logging
from typing import Any

from shared.constants import STATUS_COMPLETED
from shared.dynamodb_utils import get_song
from shared.error_handling import NotFoundError, handle_errors
from shared.response import success
from shared.s3_utils import get_lyrics_url, get_stem_urls

logger = logging.getLogger(__name__)


@handle_errors
def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    user_id: str = event["requestContext"]["authorizer"]["claims"]["sub"]
    song_id: str = event["pathParameters"]["songId"]
    logger.info("Get song request: userId=%s songId=%s", user_id, song_id)

    song = get_song(user_id, song_id)
    if song is None:
        raise NotFoundError(f"Song '{song_id}' not found")

    if song.get("status") == STATUS_COMPLETED:
        song["stemUrls"] = get_stem_urls(user_id, song_id)
        song["lyricsUrl"] = get_lyrics_url(user_id, song_id)

    return success(song)

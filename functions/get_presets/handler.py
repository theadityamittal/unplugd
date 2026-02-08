"""GET /presets — return available mixing presets."""

from __future__ import annotations

import logging
from typing import Any

from shared.constants import MIXING_PRESETS
from shared.error_handling import handle_errors
from shared.response import success

logger = logging.getLogger(__name__)


@handle_errors
def lambda_handler(_event: dict[str, Any], _context: Any) -> dict[str, Any]:
    logger.info("Get presets request")
    return success(MIXING_PRESETS)

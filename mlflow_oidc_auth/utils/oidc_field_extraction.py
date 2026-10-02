"""
OIDC field extraction utilities.

Provides functions to extract user information fields from OIDC userinfo
and token payloads using configurable field names.
"""

from typing import Any, Dict, List, Optional

from mlflow_oidc_auth.config import config
from mlflow_oidc_auth.logger import get_logger

logger = get_logger()


def extract_field_from_payload(
    payload: Dict[str, Any],
    field_list: List[str],
    field_type_name: str,
) -> tuple[Optional[str], Optional[str]]:
    """
    Extract a field value from a payload using a configured list of field names.

    This function attempts to extract a value from the payload by iterating through
    the configured field names in order and returning the first non-empty value found.
    Empty or whitespace-only values are treated as missing, so the next configured
    field is tried. The value must be a string; non-string values are rejected with an error.

    Parameters:
        payload: Dictionary containing the fields to extract from (e.g., userinfo or token payload)
        field_list: List of field names to try in order
        field_type_name: Human-readable name of the field type (e.g., "username", "display_name")

    Returns:
        Tuple of (value, error_message) where:
        - value is the extracted string value or None if not found/invalid
        - error_message is an error string if extraction failed, None if successful
    """
    if not field_list:
        return None, f"No {field_type_name} fields configured"

    for field in field_list:
        value = payload.get(field)
        if value is not None:
            if not isinstance(value, str):
                error_msg = f"Invalid OIDC {field_type_name} field: {field} is not a string"
                logger.error(error_msg)
                return None, error_msg
            if not value.strip():
                continue
            return value, None

    # No field found
    label = field_type_name.replace("_", " ")
    if len(field_list) == 1:
        return None, f"Could not determine {label}: the identity provider did not provide a non-empty value for the '{field_list[0]}' claim"
    claims = ", ".join(f"'{field}'" for field in field_list)
    return None, f"Could not determine {label}: the identity provider did not provide a non-empty value for any of the claims {claims}"


def extract_username(payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """
    Extract username from OIDC userinfo or token payload.

    Uses configured OIDC_USERNAME_FIELD list to determine which fields to check.

    Parameters:
        payload: OIDC userinfo or token payload dictionary

    Returns:
        Tuple of (username, error_message) where:
        - username is the extracted username (lowercased) or None if not found/invalid
        - error_message is an error string if extraction failed, None if successful
    """
    value, error_msg = extract_field_from_payload(payload, config.OIDC_USERNAME_FIELD, "username")
    if error_msg:
        return None, error_msg
    return value.lower() if value else None, None


def extract_display_name(payload: Dict[str, Any], fallback: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
    """
    Extract display name from OIDC userinfo or token payload.

    Uses configured OIDC_DISPLAY_NAME_FIELD list to determine which fields to check.
    If no configured field yields a usable value and a fallback is given, the fallback
    is returned instead of an error, so a missing display name never blocks login.

    Parameters:
        payload: OIDC userinfo or token payload dictionary
        fallback: Value to use when no display name can be extracted (typically the username)

    Returns:
        Tuple of (display_name, error_message) where:
        - display_name is the extracted display name or None if not found/invalid
        - error_message is an error string if extraction failed, None if successful
    """
    value, error_msg = extract_field_from_payload(payload, config.OIDC_DISPLAY_NAME_FIELD, "display_name")
    if error_msg and fallback:
        logger.warning(f"{error_msg}; using '{fallback}' as display name")
        return fallback, None
    return value, error_msg


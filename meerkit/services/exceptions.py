from meerkit.exceptions import (
    ExternalServiceError,
    PersistenceError,
    ResourceNotFoundError,
    ValidationError,
)


class AuthServiceError(ValidationError):
    default_error_code = "auth_service_error"


class DuplicateAppUserError(AuthServiceError):
    default_error_code = "duplicate_app_user"


class InvalidInstagramCredentialsError(AuthServiceError):
    default_error_code = "invalid_instagram_credentials"


class InvalidCookieStringError(AuthServiceError):
    default_error_code = "invalid_cookie_string"


class InvalidUpdateRequestError(AuthServiceError):
    default_error_code = "invalid_update_request"


class AuthStorageError(PersistenceError):
    default_error_code = "auth_storage_error"


class PredictionError(ValidationError):
    default_error_code = "prediction_error"


class InvalidRelationshipTypeError(PredictionError):
    default_error_code = "invalid_relationship_type"


class InvalidPredictionInputError(PredictionError):
    default_error_code = "invalid_prediction_input"


class TargetResolutionError(PredictionError):
    default_error_code = "target_resolution_error"
    default_retryable = True


class PredictionNotFoundError(ResourceNotFoundError):
    default_error_code = "prediction_not_found"


class AutomationServiceError(ValidationError):
    default_error_code = "automation_service_error"


class InvalidListTypeError(AutomationServiceError):
    default_error_code = "invalid_list_type"


class InvalidPrimaryAccountError(AutomationServiceError):
    default_error_code = "invalid_primary_account"


class InvalidActionStateError(AutomationServiceError):
    default_error_code = "invalid_action_state"


class ActionNotFoundError(ResourceNotFoundError):
    default_error_code = "automation_action_not_found"


class ActionOwnershipError(AutomationServiceError):
    default_error_code = "action_ownership_error"


class DownloadError(ExternalServiceError):
    default_error_code = "download_error"


class ImageDownloadRequestError(DownloadError):
    default_error_code = "image_download_request_error"


class InvalidImageContentError(DownloadError):
    default_error_code = "invalid_image_content"
    default_retryable = False


class RelationshipCacheError(PersistenceError):
    default_error_code = "relationship_cache_error"


class MissingCurlPatternError(ExternalServiceError):
    default_error_code = "missing_curl_pattern"

    def __init__(
        self,
        internal_name: str,
        display_name: str = "",
        message: str | None = None,
    ) -> None:
        self.internal_name = internal_name
        self.display_name = display_name
        super().__init__(
            message or f"Missing API curl pattern: {display_name or internal_name}",
        )

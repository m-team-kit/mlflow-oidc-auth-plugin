"""
Tests for the logger module.

This module contains comprehensive tests for the get_logger function
to achieve 100% test coverage.
"""

import logging
import os
from unittest.mock import Mock, call, patch

from mlflow_oidc_auth.logger import get_logger

# get_logger() also mutes this MLflow logger, so it is looked up on first call too
TYPE_HINTS_LOGGER = "mlflow.types.type_hints"


class TestGetLogger:
    """Test cases for the get_logger function."""

    def _make_mock_logger(self):
        """Create a logger mock with required attributes for get_logger.

        The real implementation checks ``handlers`` and ``propagate`` before
        modifying the logger, so our mocks must provide those attributes or
        else attribute access will raise.
        """
        mock_logger = Mock(spec=logging.Logger)
        mock_logger.handlers = []
        mock_logger.propagate = False
        return mock_logger

    def _patch_get_logger(self, mock_logger):
        """Patch logging.getLogger to return mock_logger, routing the MLflow
        type-hints logger to a separate mock so its setLevel call is kept apart."""
        self.type_hints_logger = Mock(spec=logging.Logger)
        return patch("logging.getLogger", side_effect=lambda name: self.type_hints_logger if name == TYPE_HINTS_LOGGER else mock_logger)

    def setup_method(self):
        """Reset the global logger instance before each test."""

        # Reset the global _logger to None
        import mlflow_oidc_auth.logger

        mlflow_oidc_auth.logger._logger = None

        # Ensure ambient shell env doesn't affect default-level tests
        for key in ["LOGGING_LOGGER_NAME", "LOG_LEVEL"]:
            if key in os.environ:
                del os.environ[key]

    def teardown_method(self):
        """Clean up after each test."""
        # Reset the global _logger
        import mlflow_oidc_auth.logger

        mlflow_oidc_auth.logger._logger = None
        # Clear environment variables
        for key in ["LOGGING_LOGGER_NAME", "LOG_LEVEL"]:
            if key in os.environ:
                del os.environ[key]

    def test_get_logger_first_call_sets_up_logger(self):
        """Test that first call to get_logger sets up the logger."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            result = get_logger()

            # Should call getLogger with default name
            assert mock_get_logger.call_args_list == [call("uvicorn"), call(TYPE_HINTS_LOGGER)]
            # Should set level to INFO
            mock_logger.setLevel.assert_called_once_with(logging.INFO)
            # Should set propagate to True
            assert mock_logger.propagate == True
            # Should return the logger
            assert result is mock_logger

    def test_get_logger_subsequent_calls_return_same_logger(self):
        """Test that subsequent calls return the same logger instance."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            result1 = get_logger()
            result2 = get_logger()

            # getLogger should only be called on the first get_logger() call
            assert mock_get_logger.call_args_list == [call("uvicorn"), call(TYPE_HINTS_LOGGER)]
            # Both results should be the same
            assert result1 is result2
            assert result1 is mock_logger

    @patch.dict(os.environ, {"LOGGING_LOGGER_NAME": "custom_logger"})
    def test_get_logger_with_custom_logger_name(self):
        """Test get_logger with custom LOGGING_LOGGER_NAME."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            result = get_logger()

            assert mock_get_logger.call_args_list == [call("custom_logger"), call(TYPE_HINTS_LOGGER)]
            assert result is mock_logger

    @patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"})
    def test_get_logger_with_debug_level(self):
        """Test get_logger with LOG_LEVEL set to DEBUG."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            mock_logger.setLevel.assert_called_once_with(logging.DEBUG)

    @patch.dict(os.environ, {"LOG_LEVEL": "WARNING"})
    def test_get_logger_with_warning_level(self):
        """Test get_logger with LOG_LEVEL set to WARNING."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            mock_logger.setLevel.assert_called_once_with(logging.WARNING)

    @patch.dict(os.environ, {"LOG_LEVEL": "ERROR"})
    def test_get_logger_with_error_level(self):
        """Test get_logger with LOG_LEVEL set to ERROR."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            mock_logger.setLevel.assert_called_once_with(logging.ERROR)

    @patch.dict(os.environ, {"LOG_LEVEL": "CRITICAL"})
    def test_get_logger_with_critical_level(self):
        """Test get_logger with LOG_LEVEL set to CRITICAL."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            mock_logger.setLevel.assert_called_once_with(logging.CRITICAL)

    @patch.dict(os.environ, {"LOG_LEVEL": "INVALID"})
    def test_get_logger_with_invalid_log_level_defaults_to_info(self):
        """Test get_logger with invalid LOG_LEVEL defaults to INFO."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            # Should default to INFO for invalid level
            mock_logger.setLevel.assert_called_once_with(logging.INFO)

    def test_get_logger_propagate_set_to_true(self):
        """Test that propagate is set to True."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            assert mock_logger.propagate == True

    @patch.dict(os.environ, {"LOGGING_LOGGER_NAME": "test_name", "LOG_LEVEL": "DEBUG"})
    def test_get_logger_with_both_env_vars(self):
        """Test get_logger with both LOGGING_LOGGER_NAME and LOG_LEVEL set."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            result = get_logger()

            assert mock_get_logger.call_args_list == [call("test_name"), call(TYPE_HINTS_LOGGER)]
            mock_logger.setLevel.assert_called_once_with(logging.DEBUG)
            assert mock_logger.propagate == True
            assert result is mock_logger

    def test_get_logger_logger_name_default(self):
        """Test that default logger name is 'uvicorn'."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            assert mock_get_logger.call_args_list == [call("uvicorn"), call(TYPE_HINTS_LOGGER)]

    def test_get_logger_log_level_default(self):
        """Test that default log level is INFO."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger) as mock_get_logger:

            get_logger()

            mock_logger.setLevel.assert_called_once_with(logging.INFO)

    def test_get_logger_mutes_mlflow_type_hints_logger(self):
        """Test that the MLflow type-hints logger is set to ERROR."""
        mock_logger = self._make_mock_logger()
        with self._patch_get_logger(mock_logger):
            get_logger()

            self.type_hints_logger.setLevel.assert_called_once_with(logging.ERROR)

    def test_get_logger_adds_stream_handler_if_none(self):
        """Logger without handlers should gain a StreamHandler."""
        # create a real logger object before patching
        real_logger = logging.getLogger("test_no_handlers")
        real_logger.handlers = []
        with patch("logging.getLogger", return_value=real_logger) as mock_get_logger:
            result = get_logger()

            # after initialization there should be exactly one handler added
            assert len(result.handlers) == 1
            assert isinstance(result.handlers[0], logging.StreamHandler)

    def test_get_logger_does_not_duplicate_handlers(self):
        """Calling get_logger multiple times shouldn't add extra handlers."""
        real_logger = logging.getLogger("test_duplicate")
        real_logger.handlers = []
        with patch("logging.getLogger", return_value=real_logger) as mock_get_logger:
            first = get_logger()
            second = get_logger()
            assert first is second
            assert len(first.handlers) == 1  # still only the one handler

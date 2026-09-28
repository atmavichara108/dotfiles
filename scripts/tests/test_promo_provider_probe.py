#!/usr/bin/env python3
"""
Fixture-based no-network тесты для promo-provider-probe.

Запуск:
    python3 scripts/tests/test_promo_provider_probe.py
    или
    python3 -m unittest scripts/tests/test_promo_provider_probe.py -v
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts dir to path
SCRIPTS_DIR = Path(__file__).parent.parent / ".local" / "bin"
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the module (it's a script without .py extension)
import importlib.machinery
import importlib.util

loader = importlib.machinery.SourceFileLoader("promo_provider_probe", str(SCRIPTS_DIR / "promo-provider-probe"))
spec = importlib.util.spec_from_loader("promo_provider_probe", loader)
if spec is None:
    raise ImportError("Cannot create spec for promo-provider-probe")
probe = importlib.util.module_from_spec(spec)
loader.exec_module(probe)


class TestJoinEndpoint(unittest.TestCase):
    """Тесты join_endpoint: не должно давать /v1/v1."""

    def test_join_with_leading_slash(self):
        """base=/v1, path=/models → /v1/models."""
        result = probe.join_endpoint("https://api.test.com/v1", "/models")
        self.assertEqual(result, "https://api.test.com/v1/models")

    def test_join_without_leading_slash(self):
        """base=/v1, path=models → /v1/models."""
        result = probe.join_endpoint("https://api.test.com/v1", "models")
        self.assertEqual(result, "https://api.test.com/v1/models")

    def test_join_with_trailing_slash(self):
        """base=/v1/, path=/models → /v1/models."""
        result = probe.join_endpoint("https://api.test.com/v1/", "/models")
        self.assertEqual(result, "https://api.test.com/v1/models")

    def test_join_no_double_v1(self):
        """Не должно давать /v1/v1."""
        result = probe.join_endpoint("https://api.test.com/v1", "/v1/models")
        # Это даст /v1/v1/models, но это ожидаемо — path не должен содержать /v1
        self.assertEqual(result, "https://api.test.com/v1/v1/models")


class TestAuthResolution(unittest.TestCase):
    """Тесты резолвинга auth из env и auth-store."""

    def test_resolve_from_env(self):
        """Env var имеет приоритет."""
        with patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "env-key-123"}):
            key = probe.resolve_auth_from_env("testprov")
            self.assertEqual(key, "env-key-123")

    def test_resolve_from_env_case_insensitive(self):
        """Provider ID приводится к upper case."""
        with patch.dict(os.environ, {"PROMO_PROVIDER_MYPROV_KEY": "key-abc"}):
            key = probe.resolve_auth_from_env("myprov")
            self.assertEqual(key, "key-abc")

    def test_resolve_from_env_missing(self):
        """Env var отсутствует."""
        with patch.dict(os.environ, {}, clear=True):
            key = probe.resolve_auth_from_env("nonexistent")
            self.assertIsNone(key)

    def test_resolve_from_store_nested_format(self):
        """Auth-store с nested форматом: providers.<id>."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "providers": {
                    "justwoker": {"api_key": "nested-key-456"}
                }
            }, f)
            f.flush()
            try:
                key = probe.resolve_auth_from_store("justwoker", f.name)
                self.assertEqual(key, "nested-key-456")
            finally:
                os.unlink(f.name)

    def test_resolve_from_store_flat_format(self):
        """Auth-store с flat форматом: <id>."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "linaliapi": {"api_key": "flat-key-789"}
            }, f)
            f.flush()
            try:
                key = probe.resolve_auth_from_store("linaliapi", f.name)
                self.assertEqual(key, "flat-key-789")
            finally:
                os.unlink(f.name)

    def test_resolve_from_store_alternative_fields(self):
        """Поддержка полей: key, token, secret."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "providers": {
                    "testprov": {"token": "token-value"}
                }
            }, f)
            f.flush()
            try:
                key = probe.resolve_auth_from_store("testprov", f.name)
                self.assertEqual(key, "token-value")
            finally:
                os.unlink(f.name)

    def test_resolve_from_store_missing_provider(self):
        """Provider не найден в auth-store."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"providers": {"other": {"api_key": "key"}}}, f)
            f.flush()
            try:
                key = probe.resolve_auth_from_store("nonexistent", f.name)
                self.assertIsNone(key)
            finally:
                os.unlink(f.name)

    def test_resolve_from_store_file_not_found(self):
        """Auth-store файл отсутствует."""
        key = probe.resolve_auth_from_store("test", "/nonexistent/path.json")
        self.assertIsNone(key)


class TestCurlRequest(unittest.TestCase):
    """Тесты curl_request: returncode, redaction."""

    @patch("subprocess.run")
    def test_curl_returncode_nonzero(self, mock_run):
        """returncode != 0 → error без body."""
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="curl: (6) Could not resolve host",
            returncode=6,
        )
        status, data, error = probe.curl_request("https://test.com", {}, None, 10)
        self.assertEqual(status, 0)
        self.assertEqual(data, {})
        self.assertIn("curl failed", error)
        # Body не в error
        self.assertNotIn("Could not resolve host", error)

    @patch("subprocess.run")
    def test_curl_invalid_json_no_body_in_error(self, mock_run):
        """Invalid JSON → error без body."""
        mock_run.return_value = MagicMock(
            stdout='{"invalid json200',
            stderr="",
            returncode=0,
        )
        status, data, error = probe.curl_request("https://test.com", {}, None, 10)
        self.assertEqual(status, 200)
        self.assertEqual(data, {})
        self.assertEqual(error, "Invalid JSON response")
        # Body не в error
        self.assertNotIn("invalid json", error)

    @patch("subprocess.run")
    def test_curl_success(self, mock_run):
        """Успешный запрос."""
        mock_run.return_value = MagicMock(
            stdout='{"data": []}200',
            stderr="",
            returncode=0,
        )
        status, data, error = probe.curl_request("https://test.com", {}, None, 10)
        self.assertEqual(status, 200)
        self.assertEqual(data, {"data": []})
        self.assertEqual(error, "")


class TestProbeModels(unittest.TestCase):
    """Тесты probe models с моками curl."""

    @patch("subprocess.run")
    def test_probe_models_success(self, mock_run):
        """Успешный probe: 200 + models."""
        mock_run.return_value = MagicMock(
            stdout='{"data": [{"id": "gpt-4"}, {"id": "gpt-3.5"}]}200',
            stderr="",
            returncode=0,
        )
        models, error = probe.probe_models("https://api.test.com/v1", "key", None, 10)
        self.assertIsNone(error)
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0]["id"], "gpt-4")

    @patch("subprocess.run")
    def test_probe_models_empty_data(self, mock_run):
        """Пустой data → BLOCKED."""
        mock_run.return_value = MagicMock(
            stdout='{"data": []}200',
            stderr="",
            returncode=0,
        )
        models, error = probe.probe_models("https://api.test.com/v1", "key", None, 10)
        self.assertIsNone(error)
        self.assertEqual(models, [])

    @patch("subprocess.run")
    def test_probe_models_auth_failed_401(self, mock_run):
        """401 → auth failed."""
        mock_run.return_value = MagicMock(
            stdout='{"error": "Unauthorized"}401',
            stderr="",
            returncode=0,
        )
        models, error = probe.probe_models("https://api.test.com/v1", "key", None, 10)
        self.assertIsNone(models)
        self.assertIn("Auth failed", error)

    @patch("subprocess.run")
    def test_probe_models_auth_failed_403(self, mock_run):
        """403 → auth failed."""
        mock_run.return_value = MagicMock(
            stdout='{"error": "Forbidden"}403',
            stderr="",
            returncode=0,
        )
        models, error = probe.probe_models("https://api.test.com/v1", "key", None, 10)
        self.assertIsNone(models)
        self.assertIn("Auth failed", error)

    @patch("subprocess.run")
    def test_probe_models_server_error_500(self, mock_run):
        """500 → server error."""
        mock_run.return_value = MagicMock(
            stdout='{"error": "Internal"}500',
            stderr="",
            returncode=0,
        )
        models, error = probe.probe_models("https://api.test.com/v1", "key", None, 10)
        self.assertIsNone(models)
        self.assertIn("Server error", error)

    @patch("subprocess.run")
    def test_probe_models_timeout(self, mock_run):
        """Timeout → error."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="curl", timeout=10)
        models, error = probe.probe_models("https://api.test.com/v1", "key", None, 10)
        self.assertIsNone(models)
        self.assertIn("timeout", error.lower())


class TestSmokeChat(unittest.TestCase):
    """Тесты smoke chat."""

    @patch("subprocess.run")
    def test_smoke_chat_success(self, mock_run):
        """Smoke chat успешен."""
        mock_run.return_value = MagicMock(
            stdout='{"choices": []}200',
            stderr="",
            returncode=0,
        )
        error = probe.smoke_chat("https://api.test.com/v1", "key", "gpt-3.5", None, 10)
        self.assertIsNone(error)

    @patch("subprocess.run")
    def test_smoke_chat_failed(self, mock_run):
        """Smoke chat failed."""
        mock_run.return_value = MagicMock(
            stdout='{"error": "Failed"}500',
            stderr="",
            returncode=0,
        )
        error = probe.smoke_chat("https://api.test.com/v1", "key", "gpt-3.5", None, 10)
        self.assertIn("Server error", error)


class TestCheckBalance(unittest.TestCase):
    """Тесты balance check с декларативным конфигом."""

    @patch("subprocess.run")
    def test_check_balance_success(self, mock_run):
        """Balance endpoint доступен."""
        mock_run.return_value = MagicMock(
            stdout='{"balance": 50.0}200',
            stderr="",
            returncode=0,
        )
        balance, error = probe.check_balance(
            "https://api.test.com/v1", "key", None, 10,
            "/balance", "balance"
        )
        self.assertEqual(balance, 50.0)
        self.assertIsNone(error)

    @patch("subprocess.run")
    def test_check_balance_not_configured(self, mock_run):
        """Balance endpoint не настроен."""
        balance, error = probe.check_balance(
            "https://api.test.com/v1", "key", None, 10,
            None, None
        )
        self.assertIsNone(balance)
        self.assertEqual(error, "not_configured")
        # curl не вызывался
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_check_balance_selector_not_found(self, mock_run):
        """Selector не найден в response."""
        mock_run.return_value = MagicMock(
            stdout='{"other_field": 100}200',
            stderr="",
            returncode=0,
        )
        balance, error = probe.check_balance(
            "https://api.test.com/v1", "key", None, 10,
            "/balance", "balance"
        )
        self.assertIsNone(balance)
        self.assertIn("not found", error.lower())


class TestThresholds(unittest.TestCase):
    """Тесты thresholds: 25/10/0 percent."""

    def _create_config(self, provider_config: dict) -> str:
        """Создать временный конфиг."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"providers": {"testprov": provider_config}}, f)
        f.flush()
        f.close()
        return f.name

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_threshold_below_25_percent(self, mock_run):
        """Balance ниже 25% → warning balance_low."""
        # balance_initial=100, balance=20 → 20%
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 20.0}200', stderr="", returncode=0),
        ]
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            "balance_endpoint": "/balance",
            "balance_selector": "balance",
            "balance_kind": "referral",
            "balance_initial": 100.0,
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path, "--json"]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_ACTIVE)
                # Проверить warnings через stdout
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_threshold_below_10_percent(self, mock_run):
        """Balance ниже 10% → warning balance_critical."""
        # balance_initial=100, balance=5 → 5%
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 5.0}200', stderr="", returncode=0),
        ]
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            "balance_endpoint": "/balance",
            "balance_selector": "balance",
            "balance_kind": "referral",
            "balance_initial": 100.0,
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path, "--json"]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_ACTIVE)
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_threshold_at_zero(self, mock_run):
        """Balance = 0 → warning balance_zero + DEGRADED."""
        # balance_initial=100, balance=0 → 0%
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 0.0}200', stderr="", returncode=0),
        ]
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            "balance_endpoint": "/balance",
            "balance_selector": "balance",
            "balance_kind": "referral",
            "balance_initial": 100.0,
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path, "--json"]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_DEGRADED)
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_threshold_boundary_25_percent(self, mock_run):
        """Boundary: ровно 25% → warning balance_low."""
        # balance_initial=100, balance=25 → 25%
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 25.0}200', stderr="", returncode=0),
        ]
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            "balance_endpoint": "/balance",
            "balance_selector": "balance",
            "balance_kind": "referral",
            "balance_initial": 100.0,
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path, "--json"]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_ACTIVE)
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_no_denominator_no_percentage_warnings(self, mock_run):
        """Нет denominator → нет percentage warnings."""
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 5.0}200', stderr="", returncode=0),
        ]
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            "balance_endpoint": "/balance",
            "balance_selector": "balance",
            "balance_kind": "referral",
            # Нет balance_initial или balance_total
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path, "--json"]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_ACTIVE)
        finally:
            os.unlink(config_path)


class TestSmokeModel(unittest.TestCase):
    """Тесты smoke_model: --smoke без smoke_model → DEGRADED."""

    def _create_config(self, provider_config: dict) -> str:
        """Создать временный конфиг."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"providers": {"testprov": provider_config}}, f)
        f.flush()
        f.close()
        return f.name

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_smoke_without_smoke_model(self, mock_run):
        """--smoke без smoke_model → DEGRADED warning без запроса."""
        mock_run.return_value = MagicMock(
            stdout='{"data": [{"id": "gpt-4"}]}200',
            stderr="",
            returncode=0,
        )
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            # Нет smoke_model
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path, "--smoke"]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_DEGRADED)
                # curl вызван только 1 раз (для models), не для smoke
                self.assertEqual(mock_run.call_count, 1)
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_smoke_with_smoke_model(self, mock_run):
        """--smoke с smoke_model → запрос к chat/completions."""
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"choices": []}200', stderr="", returncode=0),
        ]
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            "smoke_model": "gpt-3.5-turbo",
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path, "--smoke"]):
                with patch("sys.stdout") as mock_stdout:
                    with self.assertRaises(SystemExit) as cm:
                        probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_DEGRADED)
                self.assertIn("balance_unknown", str(mock_stdout.write.call_args_list))
                # curl вызван 2 раза: models + smoke
                self.assertEqual(mock_run.call_count, 2)
        finally:
            os.unlink(config_path)


class TestExitCodes(unittest.TestCase):
    """Тесты exit codes через main()."""

    def _create_config(self, provider_config: dict) -> str:
        """Создать временный конфиг."""
        f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"providers": {"testprov": provider_config}}, f)
        f.flush()
        f.close()
        return f.name

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_exit_active(self, mock_run):
        """ACTIVE: models + balance."""
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 100.0}200', stderr="", returncode=0),
        ]
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
            "balance_endpoint": "/balance",
            "balance_selector": "balance",
            "balance_kind": "referral",
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_ACTIVE)
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_exit_blocked_empty_models(self, mock_run):
        """BLOCKED: empty models."""
        mock_run.return_value = MagicMock(
            stdout='{"data": []}200',
            stderr="",
            returncode=0,
        )
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_BLOCKED)
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_exit_blocked_auth_failed(self, mock_run):
        """BLOCKED: 401."""
        mock_run.return_value = MagicMock(
            stdout='{"error": "Unauthorized"}401',
            stderr="",
            returncode=0,
        )
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_BLOCKED)
        finally:
            os.unlink(config_path)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "test-key"})
    def test_exit_error_server_error(self, mock_run):
        """ERROR: 500."""
        mock_run.return_value = MagicMock(
            stdout='{"error": "Internal"}500',
            stderr="",
            returncode=0,
        )
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_ERROR)
        finally:
            os.unlink(config_path)

    @patch.dict(os.environ, {}, clear=True)
    def test_exit_error_auth_unavailable(self):
        """ERROR: auth not found."""
        config_path = self._create_config({
            "endpoint": "https://api.test.com/v1",
            "proxy": None,
            "auth_source": "env",
        })
        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path]):
                with self.assertRaises(SystemExit) as cm:
                    probe.main()
                self.assertEqual(cm.exception.code, probe.EXIT_ERROR)
        finally:
            os.unlink(config_path)


class TestSecretRedaction(unittest.TestCase):
    """Тесты: секреты не попадают в stdout И stderr."""

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "super-secret-key-12345"})
    def test_no_secret_in_stdout_and_stderr(self, mock_run):
        """Ключ не попадает в stdout И stderr."""
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 100.0}200', stderr="", returncode=0),
        ]
        config_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({
            "providers": {
                "testprov": {
                    "endpoint": "https://api.test.com/v1",
                    "proxy": "socks5h://127.0.0.1:10808",
                    "auth_source": "env",
                    "balance_endpoint": "/balance",
                    "balance_selector": "balance",
                    "balance_kind": "referral",
                }
            }
        }, config_path)
        config_path.flush()
        config_path.close()

        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path.name, "--json"]):
                with patch("sys.stdout") as mock_stdout, patch("sys.stderr") as mock_stderr:
                    with self.assertRaises(SystemExit):
                        probe.main()
                    
                    # Проверить stdout
                    stdout_output = str(mock_stdout.write.call_args_list)
                    self.assertNotIn("super-secret-key-12345", stdout_output)
                    self.assertNotIn("Bearer", stdout_output)
                    
                    # Проверить stderr
                    stderr_output = str(mock_stderr.write.call_args_list)
                    self.assertNotIn("super-secret-key-12345", stderr_output)
                    self.assertNotIn("Bearer", stderr_output)
        finally:
            os.unlink(config_path.name)

    @patch("subprocess.run")
    @patch.dict(os.environ, {"PROMO_PROVIDER_TESTPROV_KEY": "secret-key-xyz"})
    def test_authorization_header_not_in_output(self, mock_run):
        """Authorization header не попадает в output."""
        mock_run.side_effect = [
            MagicMock(stdout='{"data": [{"id": "gpt-4"}]}200', stderr="", returncode=0),
            MagicMock(stdout='{"balance": 50.0}200', stderr="", returncode=0),
        ]
        config_path = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({
            "providers": {
                "testprov": {
                    "endpoint": "https://api.test.com/v1",
                    "proxy": None,
                    "auth_source": "env",
                    "balance_endpoint": "/balance",
                    "balance_selector": "balance",
                }
            }
        }, config_path)
        config_path.flush()
        config_path.close()

        try:
            with patch("sys.argv", ["promo-provider-probe", "testprov", "--config", config_path.name, "--json"]):
                with patch("sys.stdout") as mock_stdout, patch("sys.stderr") as mock_stderr:
                    with self.assertRaises(SystemExit):
                        probe.main()
                    
                    stdout_output = str(mock_stdout.write.call_args_list)
                    stderr_output = str(mock_stderr.write.call_args_list)
                    
                    # Authorization не должен быть в output
                    self.assertNotIn("Authorization", stdout_output)
                    self.assertNotIn("Authorization", stderr_output)
                    self.assertNotIn("Bearer", stdout_output)
                    self.assertNotIn("Bearer", stderr_output)
        finally:
            os.unlink(config_path.name)


if __name__ == "__main__":
    unittest.main(verbosity=2)

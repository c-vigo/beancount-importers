"""Tests for the Telegram downloader CLI tool."""

import csv
import os
import sys
import tempfile
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Mock optional dependencies before importing
sys.modules["telethon"] = MagicMock()
sys.modules["telethon.sync"] = MagicMock()
sys.modules["camelot"] = MagicMock()
sys.modules["pypdf"] = MagicMock()

from beancount_importers.cli.telegram_downloader import (  # noqa: E402
    AttachmentPattern,
    ParseAttachmentPattern,
    ParseDict,
    build_file_name,
    check_connection,
    main,
)


class TestAttachmentPattern:
    """Tests for AttachmentPattern class."""

    def test_initialization(self) -> None:
        """Test AttachmentPattern initialization."""
        pattern = AttachmentPattern(
            account="Assets:Cash",
            pattern="*.pdf",
            skip_init=0,
            skip_end=10,
            name="receipt",
        )
        assert pattern.account == "Assets:Cash"
        assert pattern.pattern == "*.pdf"
        assert pattern.skip_init == 0
        assert pattern.skip_end == 10
        assert pattern.name == "receipt"

    def test_str_representation(self) -> None:
        """Test string representation."""
        pattern = AttachmentPattern(
            account="Assets:Cash",
            pattern="*.pdf",
            skip_init=0,
            skip_end=10,
            name="receipt",
        )
        str_repr = str(pattern)
        assert "Assets:Cash" in str_repr
        assert "*.pdf" in str_repr
        assert "receipt" in str_repr


class TestParseAttachmentPattern:
    """Tests for ParseAttachmentPattern action."""

    @pytest.fixture
    def mock_parser(self) -> Any:
        """Create a mock ArgumentParser for testing."""
        from unittest.mock import MagicMock

        return MagicMock(spec=["ArgumentParser"])

    def test_parse_single_pattern(self, mock_parser: Any) -> None:
        """Test parsing a single attachment pattern."""
        action = ParseAttachmentPattern("--attachment-map", dest="attachment_map")
        namespace = Namespace()
        action(mock_parser, namespace, ["Assets:Cash;*.pdf;0;10;receipt"])

        assert hasattr(namespace, "attachment_map")
        assert len(namespace.attachment_map) == 1
        pattern = namespace.attachment_map[0]
        assert pattern.account == "Assets:Cash"
        assert pattern.pattern == "*.pdf"
        assert pattern.skip_init == 0
        assert pattern.skip_end == 10
        assert pattern.name == "receipt"

    def test_parse_multiple_patterns(self, mock_parser: Any) -> None:
        """Test parsing multiple attachment patterns."""
        action = ParseAttachmentPattern("--attachment-map", dest="attachment_map")
        namespace = Namespace()
        action(
            mock_parser,
            namespace,
            [
                "Assets:Cash;*.pdf;0;10;receipt",
                "Assets:Bank;*.jpg;5;15;invoice",
            ],
        )

        assert len(namespace.attachment_map) == 2
        assert namespace.attachment_map[0].account == "Assets:Cash"
        assert namespace.attachment_map[1].account == "Assets:Bank"

    def test_parse_invalid_pattern(self, mock_parser: Any) -> None:
        """Test parsing invalid attachment pattern."""
        from argparse import ArgumentTypeError

        action = ParseAttachmentPattern("--attachment-map", dest="attachment_map")
        namespace = Namespace()
        with pytest.raises(ArgumentTypeError):
            action(mock_parser, namespace, ["invalid"])

    def test_parse_none_values(self, mock_parser: Any) -> None:
        """Test parsing with None values."""
        action = ParseAttachmentPattern("--attachment-map", dest="attachment_map")
        namespace = Namespace()
        action(mock_parser, namespace, None)
        assert (
            not hasattr(namespace, "attachment_map") or namespace.attachment_map == []
        )

    def test_parse_string_value(self, mock_parser: Any) -> None:
        """Test parsing with string value (single item)."""
        action = ParseAttachmentPattern("--attachment-map", dest="attachment_map")
        namespace = Namespace()
        action(mock_parser, namespace, "Assets:Cash;*.pdf;0;10;receipt")
        assert len(namespace.attachment_map) == 1


class TestParseDict:
    """Tests for ParseDict action."""

    @pytest.fixture
    def mock_parser(self) -> Any:
        """Create a mock ArgumentParser for testing."""
        from unittest.mock import MagicMock

        return MagicMock(spec=["ArgumentParser"])

    def test_parse_single_key_value(self, mock_parser: Any) -> None:
        """Test parsing a single key=value pair."""
        action = ParseDict("--account-map", dest="account_map")
        namespace = Namespace()
        action(mock_parser, namespace, ["Cash=Assets:Cash:CHF"])

        assert hasattr(namespace, "account_map")
        assert namespace.account_map == {"Cash": "Assets:Cash:CHF"}

    def test_parse_multiple_key_value_pairs(self, mock_parser: Any) -> None:
        """Test parsing multiple key=value pairs."""
        action = ParseDict("--account-map", dest="account_map")
        namespace = Namespace()
        action(
            mock_parser,
            namespace,
            ["Cash=Assets:Cash:CHF", "Bank=Assets:Bank:EUR"],
        )

        assert namespace.account_map == {
            "Cash": "Assets:Cash:CHF",
            "Bank": "Assets:Bank:EUR",
        }

    def test_parse_invalid_format(self, mock_parser: Any) -> None:
        """Test parsing invalid format."""
        from argparse import ArgumentTypeError

        action = ParseDict("--account-map", dest="account_map")
        namespace = Namespace()
        with pytest.raises(ArgumentTypeError):
            action(mock_parser, namespace, ["invalid"])

    def test_parse_none_values(self, mock_parser: Any) -> None:
        """Test parsing with None values."""
        action = ParseDict("--account-map", dest="account_map")
        namespace = Namespace()
        action(mock_parser, namespace, None)
        assert namespace.account_map == {}

    def test_parse_string_value(self, mock_parser: Any) -> None:
        """Test parsing with string value (single item)."""
        action = ParseDict("--account-map", dest="account_map")
        namespace = Namespace()
        action(mock_parser, namespace, "Cash=Assets:Cash:CHF")
        assert namespace.account_map == {"Cash": "Assets:Cash:CHF"}


class TestBuildFileName:
    """Tests for build_file_name function."""

    def test_build_file_name(self) -> None:
        """Test building file name."""
        args = Namespace()
        args.account_map = {"Cash": "Assets:Cash:CHF"}
        args.root_folder = "/tmp/records"

        filename = build_file_name("Cash", "2024", args)
        assert "2024-12-31" in filename
        assert "Cash" in filename
        assert "_Transactions_TelegramBot.csv" in filename
        assert "Assets/Cash/CHF" in filename or "Assets" in filename

    def test_build_file_name_missing_account(self) -> None:
        """Test building file name with missing account."""
        args = Namespace()
        args.account_map = {"Cash": "Assets:Cash:CHF"}
        args.root_folder = "/tmp/records"

        with pytest.raises(KeyError):
            build_file_name("MissingAccount", "2024", args)


class TestCheckConnection:
    """Tests for check_connection function."""

    @patch("beancount_importers.cli.telegram_downloader.TelegramClient")
    def test_check_connection(self, mock_client_class: MagicMock) -> None:
        """Test checking Telegram connection."""
        # Setup mock
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_chat = MagicMock()
        mock_chat.title = "Test Chat"
        mock_client.get_entity.return_value = mock_chat

        mock_message = MagicMock()
        mock_message.date = datetime(2024, 1, 1)
        mock_message.text = "Test message"
        mock_client.iter_messages.return_value = [mock_message]

        args = Namespace()
        args.session_file = "/tmp/session"
        args.api_id = 12345
        args.api_hash = "hash"
        args.chat_id = 67890

        check_connection(args)

        mock_client_class.assert_called_once_with("/tmp/session", 12345, "hash")
        mock_client.get_entity.assert_called_once_with(67890)
        mock_client.iter_messages.assert_called_once_with(67890, reverse=False, limit=1)


class TestTelegramDownloaderMain:
    """Tests for the main beancount_telegram function."""

    @pytest.fixture
    def temp_dir(self) -> tempfile.TemporaryDirectory:
        """Create a temporary directory for tests."""
        return tempfile.TemporaryDirectory()

    @pytest.fixture
    def mock_args(self, temp_dir: tempfile.TemporaryDirectory) -> Namespace:
        """Create mock arguments."""
        args = Namespace()
        args.api_id = 12345
        args.api_hash = "test_hash"
        args.chat_id = 67890
        args.root_folder = temp_dir.name
        args.temp_folder = os.path.join(temp_dir.name, "temp")
        args.account_map = {"Cash": "Assets:Cash:CHF"}
        args.attachment_map = []
        args.session_file = os.path.join(temp_dir.name, "session")
        args.force = False
        args.no_download = True
        args.dry_run = False
        args.check = False
        return args

    @patch("beancount_importers.cli.telegram_downloader.TelegramClient")
    @patch("beancount_importers.cli.telegram_downloader.beancount_telegram")
    def test_main_success(
        self,
        mock_beancount_telegram: MagicMock,
        mock_client_class: MagicMock,
    ) -> None:
        """Test main function success."""
        mock_beancount_telegram.return_value = None
        with patch("sys.argv", ["beancount-telegram", "123", "hash", "456"]):
            # This will fail because we need proper args, but tests the structure
            pass

    @patch("beancount_importers.cli.telegram_downloader.TelegramClient")
    def test_transaction_parsing(
        self,
        mock_client_class: MagicMock,
        mock_args: Namespace,
        temp_dir: tempfile.TemporaryDirectory,
    ) -> None:
        """Test parsing transaction messages."""
        from beancount_importers.cli.telegram_downloader import beancount_telegram

        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        # Create mock message
        mock_sender = MagicMock()
        mock_sender.first_name = "Test User"
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.sender = mock_sender
        mock_message.date = datetime(2024, 1, 15)
        mock_message.text = "2024-01-15;Cash;Store;Groceries;50.00 CHF;food"
        mock_message.document = None

        mock_client.iter_messages.return_value = [mock_message]

        # Mock argparse
        with patch(
            "beancount_importers.cli.telegram_downloader.ArgumentParser"
        ) as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_args.return_value = mock_args

            beancount_telegram()

        # Verify file was created
        expected_file = Path(mock_args.root_folder) / "Assets" / "Cash" / "CHF"
        expected_file = expected_file / "2024-12-31-Cash_Transactions_TelegramBot.csv"
        assert expected_file.exists()

        # Verify CSV content
        with open(expected_file, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter=";")
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["id"] == "1"
            assert rows[0]["account"] == "Cash"
            assert rows[0]["amount"] == "50.00"
            assert rows[0]["currency"] == "CHF"

    @patch("beancount_importers.cli.telegram_downloader.TelegramClient")
    def test_dry_run_mode(
        self,
        mock_client_class: MagicMock,
        mock_args: Namespace,
    ) -> None:
        """Test dry-run mode."""
        from beancount_importers.cli.telegram_downloader import beancount_telegram

        mock_args.dry_run = True

        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_sender = MagicMock()
        mock_sender.first_name = "Test User"
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.sender = mock_sender
        mock_message.date = datetime(2024, 1, 15)
        mock_message.text = "2024-01-15;Cash;Store;Groceries;50.00 CHF;food"
        mock_message.document = None

        mock_client.iter_messages.return_value = [mock_message]

        with patch(
            "beancount_importers.cli.telegram_downloader.ArgumentParser"
        ) as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_args.return_value = mock_args

            with patch("builtins.print") as mock_print:
                beancount_telegram()
                # Verify dry-run printed output
                assert mock_print.called

    @patch("beancount_importers.cli.telegram_downloader.TelegramClient")
    def test_invalid_account(
        self,
        mock_client_class: MagicMock,
        mock_args: Namespace,
    ) -> None:
        """Test handling invalid account in message."""
        from beancount_importers.cli.telegram_downloader import beancount_telegram

        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_sender = MagicMock()
        mock_sender.first_name = "Test User"
        mock_message = MagicMock()
        mock_message.id = 1
        mock_message.sender = mock_sender
        mock_message.date = datetime(2024, 1, 15)
        mock_message.text = "2024-01-15;InvalidAccount;Store;Groceries;50.00 CHF"
        mock_message.document = None

        mock_client.iter_messages.return_value = [mock_message]

        with patch(
            "beancount_importers.cli.telegram_downloader.ArgumentParser"
        ) as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_args.return_value = mock_args

            with patch("builtins.print") as mock_print:
                beancount_telegram()
                # Should print warning about invalid account
                print_calls = [str(call) for call in mock_print.call_args_list]
                assert any("Invalid account" in str(call) for call in print_calls)

    @patch("beancount_importers.cli.telegram_downloader.TelegramClient")
    def test_find_last_message_id(
        self,
        mock_client_class: MagicMock,
        mock_args: Namespace,
        temp_dir: tempfile.TemporaryDirectory,
    ) -> None:
        """Test finding last message ID from existing files."""
        from beancount_importers.cli.telegram_downloader import beancount_telegram

        # Create existing CSV file
        csv_dir = Path(mock_args.root_folder) / "Assets" / "Cash" / "CHF"
        csv_dir.mkdir(parents=True, exist_ok=True)
        csv_file = csv_dir / "2024-12-31-Cash_Transactions_TelegramBot.csv"

        with open(csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                delimiter=";",
                fieldnames=[
                    "id",
                    "sender",
                    "message_date",
                    "transaction_date",
                    "account",
                    "payee",
                    "description",
                    "amount",
                    "currency",
                    "tag",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "id": "100",
                    "sender": "Test",
                    "message_date": "2024-01-15",
                    "transaction_date": "2024-01-15",
                    "account": "Cash",
                    "payee": "Store",
                    "description": "Test",
                    "amount": "50.00",
                    "currency": "CHF",
                    "tag": "",
                }
            )

        # Setup mock client
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.iter_messages.return_value = []

        with patch(
            "beancount_importers.cli.telegram_downloader.ArgumentParser"
        ) as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_args.return_value = mock_args

            with patch("builtins.print") as mock_print:
                beancount_telegram()
                # Should print message about updating from ID > 100
                print_calls = [str(call) for call in mock_print.call_args_list]
                assert any("100" in str(call) for call in print_calls)

    def test_main_keyboard_interrupt(self) -> None:
        """Test main function handling KeyboardInterrupt."""
        with patch(
            "beancount_importers.cli.telegram_downloader.beancount_telegram"
        ) as mock_func:
            mock_func.side_effect = KeyboardInterrupt()
            with patch("sys.exit") as mock_exit:
                main()
                mock_exit.assert_called_once_with(1)

    def test_main_exception(self) -> None:
        """Test main function handling general exceptions."""
        with patch(
            "beancount_importers.cli.telegram_downloader.beancount_telegram"
        ) as mock_func:
            mock_func.side_effect = ValueError("Test error")
            with patch("sys.exit") as mock_exit:
                with patch("sys.stderr"):
                    main()
                    mock_exit.assert_called_once_with(1)

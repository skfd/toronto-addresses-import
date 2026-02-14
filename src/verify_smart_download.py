"""Verify smart download logic by mocking requests."""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import date

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.download import download
from src.db import init_db, record_skipped_snapshot, get_last_snapshot_headers

# Mock DB interaction in download.py
# We actually want to test the interaction, so we might use a temp DB?
# Or just mock the db calls.

class TestSmartDownload(unittest.TestCase):
    
    @patch('src.download.requests.head')
    @patch('src.download.requests.get')
    @patch('src.download.get_last_snapshot_headers')
    def test_download_skipped_when_headers_match(self, mock_get_last, mock_get, mock_head):
        # Setup
        remote_headers = {
            "Last-Modified": "Fri, 14 Feb 2026 10:00:00 GMT",
            "Content-Length": "12345"
        }
        
        # Mock HEAD response
        mock_head_resp = MagicMock()
        mock_head_resp.headers = remote_headers
        mock_head.return_value = mock_head_resp
        
        # Mock Local DB response
        mock_get_last.return_value = {
            "remote_last_modified": "Fri, 14 Feb 2026 10:00:00 GMT",
            "remote_content_length": 12345
        }
        
        # Run
        status, data, headers = download(force=False)
        
        # Verify
        self.assertEqual(status, "SKIPPED")
        mock_get.assert_not_called()
        print("Test Skipped: PASS")

    @patch('src.download.requests.head')
    @patch('src.download.requests.get')
    @patch('src.download.get_last_snapshot_headers')
    def test_download_proceeds_when_headers_differ(self, mock_get_last, mock_get, mock_head):
        # Setup
        remote_headers = {
            "Last-Modified": "Fri, 14 Feb 2026 12:00:00 GMT", # Changed
            "Content-Length": "12345"
        }
        
        # Mock HEAD response
        mock_head_resp = MagicMock()
        mock_head_resp.headers = remote_headers
        mock_head.return_value = mock_head_resp
        
        # Mock Local DB response
        mock_get_last.return_value = {
            "remote_last_modified": "Fri, 14 Feb 2026 10:00:00 GMT",
            "remote_content_length": 12345
        }
        
        # Mock GET response (actual download)
        mock_get_resp = MagicMock()
        mock_get_resp.headers = remote_headers
        mock_get_resp.iter_content.return_value = [b"chunk"]
        mock_get.return_value = mock_get_resp
        
        # Run
        with patch('builtins.open', MagicMock()): # Don't write file
            status, data, headers = download(force=False)
        
        # Verify
        self.assertEqual(status, "DOWNLOADED")
        mock_get.assert_called_once()
        print("Test Downloaded: PASS")

if __name__ == '__main__':
    unittest.main()

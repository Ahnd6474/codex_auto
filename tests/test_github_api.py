from __future__ import annotations

import http.client
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jakal_flow.github_api import GitHubAPIError, GitHubClient


class GitHubClientTests(unittest.TestCase):
    def test_request_json_wraps_remote_disconnect(self) -> None:
        client = GitHubClient(token="demo-token")

        with mock.patch(
            "jakal_flow.github_api.urllib.request.urlopen",
            side_effect=http.client.RemoteDisconnected("Remote end closed connection without response"),
        ):
            with self.assertRaises(GitHubAPIError) as error:
                client._request_json("https://api.github.com/user")

        self.assertIn("Remote end closed connection without response", str(error.exception))


if __name__ == "__main__":
    unittest.main()

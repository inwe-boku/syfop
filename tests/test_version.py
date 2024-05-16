import re
from subprocess import CalledProcessError
from unittest.mock import patch

from syfop.version import get_version, version


def test_version():
    pattern = re.compile(r"^\d+\.\d+\.\d+")
    assert pattern.match(version)


@patch("subprocess.check_output")
def test_get_version(mock_check_output):
    # this simulates a shallow clone with --depth=1 or missing tags
    mock_check_output.side_effect = CalledProcessError(128, ["git", "describe", "--tags"])

    version = get_version()
    assert version == "0.0.0"

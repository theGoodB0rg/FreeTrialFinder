import pytest
from unittest.mock import patch
from freetrialfinder.cli import main

def test_cli_help(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "poll" in captured.out or "inspect" in captured.out

@patch("freetrialfinder.engine.FinderEngine.run_cycle")
def test_cli_poll_command(mock_run):
    mock_run.return_value = []
    exit_code = main(["poll", "--state-file", "test_state.json"])
    assert exit_code == 0
    assert mock_run.called

@patch("freetrialfinder.engine.FinderEngine.inspect")
def test_cli_inspect_command(mock_inspect):
    mock_inspect.return_value = []
    exit_code = main(["inspect"])
    assert exit_code == 0
    assert mock_inspect.called

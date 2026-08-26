from pathlib import Path
from unittest.mock import patch

from dictado_ai.config import PathsConfig, Settings
from dictado_ai.server import WhisperServerManager


def test_whisper_server_uses_configured_port() -> None:
    settings = Settings(paths=PathsConfig(project_root=Path.cwd()))

    with patch("dictado_ai.server.subprocess.Popen") as popen:
        WhisperServerManager(settings).start()

    command = popen.call_args.args[0]
    assert settings.paths.server_port == 8170
    assert command[command.index("--port") + 1] == "8170"

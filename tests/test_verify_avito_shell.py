import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "running,run_status,expected_status,expected_commands",
    [
        ("1", "0", 0, ["ps", "stop", "run", "start"]),
        ("1", "7", 7, ["ps", "stop", "run", "start"]),
        ("0", "0", 0, ["ps", "run"]),
    ],
)
def test_verify_restores_only_previously_running_bot(tmp_path, running, run_status, expected_status, expected_commands):
    docker = tmp_path / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$2\" >> \"$DOCKER_LOG\"\n"
        "case \"$2\" in\n"
        "  ps) [ \"$RUNNING\" = 1 ] && echo bot-container; exit 0 ;;\n"
        "  run) exit \"$RUN_STATUS\" ;;\n"
        "esac\n"
        "exit 0\n"
    )
    docker.chmod(0o755)
    log = tmp_path / "calls"
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", DOCKER_LOG=str(log), RUNNING=running, RUN_STATUS=run_status)
    script = Path(__file__).resolve().parents[1] / "scripts" / "verify_avito.sh"

    result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True, timeout=10)

    assert result.returncode == expected_status
    assert log.read_text().splitlines() == expected_commands

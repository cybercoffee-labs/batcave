from scheduler import build_cycle_commands, render_cycle_summary, run_scheduler


def test_build_cycle_commands_uses_expected_sequence_and_flags():
    commands = build_cycle_commands(rows=25, edge_threshold=0.1, age_threshold=300.0)

    assert [name for name, _ in commands] == [
        "agent cycle",
        "opportunity scanner",
        "system scanner",
        "alerts check",
    ]
    assert commands[0][1][-2:] == ["--cycles", "1"]
    assert commands[1][1][-4:] == ["--rows", "25", "--edge-threshold", "0.1"]
    assert commands[2][1][-4:] == ["--rows", "25", "--age-threshold", "300.0"]
    assert commands[3][1][-4:] == ["--rows", "25", "--edge-threshold", "0.1"]


def test_render_cycle_summary_shows_status_and_first_output_lines():
    summary = render_cycle_summary(
        2,
        [
            {
                "name": "agent cycle",
                "returncode": 0,
                "stdout": "agent ok\nextra",
                "stderr": "",
                "duration_seconds": 1.2,
            },
            {
                "name": "system scanner",
                "returncode": 1,
                "stdout": "",
                "stderr": "scanner failed\ntrace",
                "duration_seconds": 0.5,
            },
        ],
    )

    assert "Scheduler cycle 2" in summary
    assert "- agent cycle: ok in 1.20s" in summary
    assert "stdout: agent ok" in summary
    assert "- system scanner: failed (1) in 0.50s" in summary
    assert "stderr: scanner failed" in summary


def test_run_scheduler_runs_single_cycle_in_order():
    calls = []

    def fake_runner(name: str, command: list[str]) -> dict:
        calls.append((name, command))
        return {
            "name": name,
            "command": command,
            "returncode": 0,
            "stdout": f"{name} ok",
            "stderr": "",
            "duration_seconds": 0.1,
        }

    completed = run_scheduler(
        interval=0.0,
        rows=10,
        edge_threshold=0.2,
        age_threshold=300.0,
        runner=fake_runner,
        sleeper=lambda _: None,
        max_cycles=1,
    )

    assert completed == 1
    assert [name for name, _ in calls] == [
        "agent cycle",
        "opportunity scanner",
        "system scanner",
        "alerts check",
    ]


def test_run_scheduler_handles_keyboard_interrupt_after_first_cycle():
    call_count = {"sleep": 0}

    def fake_runner(name: str, command: list[str]) -> dict:
        return {
            "name": name,
            "command": command,
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "duration_seconds": 0.1,
        }

    def fake_sleep(_: float) -> None:
        call_count["sleep"] += 1
        raise KeyboardInterrupt

    completed = run_scheduler(
        interval=1.0,
        rows=10,
        edge_threshold=0.2,
        age_threshold=300.0,
        runner=fake_runner,
        sleeper=fake_sleep,
        max_cycles=None,
    )

    assert completed == 1
    assert call_count["sleep"] == 1

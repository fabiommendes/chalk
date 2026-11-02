import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any

import typer

app = typer.Typer()


@app.command()
def main(
    file: Annotated[
        Path | None,
        typer.Argument(
            ...,
            help="Path to the file to parse. If not provided, reads from stdin.",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            ...,
            "--output",
            "-o",
            help="Path to the output file. If not provided, prints to stdout.",
        ),
    ] = None,
):
    """
    Parse the results of calling `elm-test --report json`.
    """
    if file is not None and file.exists():
        data = file.open()
    else:
        data = sys.stdin

    try:
        result = parse_elm_tests(data)
    except ValueError as e:
        typer.echo(f"Error parsing Elm tests: {e}", err=True)
        raise typer.Exit(code=1)

    json_data = "CHALK_RESULT: " + json.dumps(result)

    if output is not None:
        output.write_text(json_data)
    else:
        typer.echo(json_data)


def parse_elm_tests(data: Iterable[str]) -> dict:
    passed = 0
    failed = 0

    # Elm-test outputs one JSON object per line
    for line in data:
        doc: dict[str, Any] = json.loads(line)
        if doc.get("event") != "testCompleted":
            continue
        # rich.print(doc)

        is_passed = doc.get("status") == "pass"
        passed += is_passed
        failed += not is_passed

    if passed == 0 and failed == 0:
        raise ValueError("No Elm test result found in the provided input.")

    result = {"pass": passed, "fail": failed}
    if passed and failed:
        result["feedback"] = f"elm-test: {passed} passed, {failed} failed"
    return result


if __name__ == "__main__":
    app()

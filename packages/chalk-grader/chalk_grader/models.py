"""
Configuration of an autograder: the `autograder` block of a question, the
profiles and their steps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ByteSize, ConfigDict, Field, model_validator

__all__ = ["Limits", "Stage", "ProfileStep", "PrepareStep", "Service", "Profile", "Autograder"]


class Limits(BaseModel):
    """
    Resource limits of an autograder run. Sizes accept units, as in "512MB"
    or "1GiB".
    """

    memory: Annotated[
        ByteSize | None,
        Field(
            description=(
                "Address space limit of the script and each process it starts (RLIMIT_AS). "
                "Runtimes that reserve large virtual areas, such as Node and the JVM, need "
                "a generous value."
            ),
        ),
    ] = None
    file_size: Annotated[
        ByteSize | None,
        Field(description="Largest file the script or its processes can write (RLIMIT_FSIZE)."),
    ] = None
    answer_size: Annotated[
        ByteSize,
        Field(description="Largest text answer that is graded. Larger answers are rejected."),
    ] = ByteSize(1024 * 1024)


class Stage(BaseModel):
    """
    Options of one step of a profile, overriding the autograder's.
    """

    timeout: Annotated[
        float | None,
        Field(description="Timeout of the step, in seconds."),
    ] = None
    limits: Annotated[
        Limits | None,
        Field(description="Resource limits of the step."),
    ] = None


class ProfileStep(Stage):
    """
    A step of a profile that runs in the sandbox, once per student.
    """

    model_config = ConfigDict(extra="forbid")

    command: Annotated[
        str,
        Field(description="Shell command of the step, run in the working directory."),
    ]
    seed: Annotated[
        dict[str, str],
        Field(
            description=(
                "Paths of the working directory filled with a copy of a path, usually in "
                "the cache, before the step. The student's files are touched after the copy, "
                "so build tools that compare modification times rebuild them."
            ),
        ),
    ] = {}


class PrepareStep(BaseModel):
    """
    The trusted step of a profile, run once per cache with the network on.
    """

    model_config = ConfigDict(extra="forbid")

    commands: Annotated[
        list[str],
        Field(description="Shell commands run in order, outside the sandbox."),
    ] = []
    timeout: Annotated[
        float | None,
        Field(description="Timeout of each command, in seconds."),
    ] = None


class Service(BaseModel):
    """
    A program the student's code talks to through the network, such as an
    HTTP server, started before the test step of each run in a sandbox of
    its own.
    """

    model_config = ConfigDict(extra="forbid")

    command: Annotated[
        str,
        Field(
            description=(
                "Shell command that starts the service, run in a copy of the template. It "
                "listens on 127.0.0.1 at `port` and may write a JUnit report to "
                "$CHALK_RESULT when it gets SIGTERM; its tests count in the grade."
            ),
        ),
    ]
    port: Annotated[
        int,
        Field(ge=1, le=65535, description="TCP port of the service, the same for the student."),
    ]
    env: Annotated[
        dict[str, str],
        Field(description="Environment variables of the service."),
    ] = {}
    start_timeout: Annotated[
        float,
        Field(gt=0, description="Seconds the service has to open the port."),
    ] = 10


class Profile(BaseModel):
    """
    Grading recipe for one ecosystem, written as data: the commands of each
    step, the environment, the files the template controls and how the
    report is read. See docs/user-manual/autograding-scripts.md.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = ""
    extends: Annotated[
        str | None,
        Field(description="Profile whose keys this one inherits. Tables are merged."),
    ] = None
    key: Annotated[
        list[str],
        Field(
            description=(
                "Template files the profile needs, such as lock files. Their contents, the "
                "probes and the prepare options select the cache directory."
            ),
        ),
    ] = []
    trusted: Annotated[
        list[str],
        Field(
            description=(
                "Files and directories of the template that replace the student's copies, "
                "or are removed from the student's project when the template lacks them."
            ),
        ),
    ] = []
    tests: Annotated[
        list[str],
        Field(description="Default test directories or files of the template."),
    ] = ["tests"]
    probe: Annotated[
        dict[str, str],
        Field(
            description=(
                "Variables set from the output of shell commands run outside the sandbox, "
                "such as the path of a toolchain."
            ),
        ),
    ] = {}
    env: Annotated[
        dict[str, str],
        Field(description="Environment variables of every step."),
    ] = {}
    unset: Annotated[
        list[str],
        Field(description="Environment variables removed in every step."),
    ] = []
    readable: Annotated[
        list[str],
        Field(description="Paths the sandbox mounts read only, such as the cache."),
    ] = ["{cache}"]
    hide: Annotated[
        list[str],
        Field(
            description=(
                "Glob patterns of files removed from the working directory before the "
                "build and test steps, such as the expected outputs of the stdio profile."
            ),
        ),
    ] = []
    vars: Annotated[
        dict[str, str],
        Field(description="Variables for the other keys. Questions override them with `vars`."),
    ] = {}
    files: Annotated[
        dict[str, str],
        Field(description="Files written to the cache directory: name -> content."),
    ] = {}
    prepare: PrepareStep = Field(default_factory=PrepareStep)
    suspicious: Annotated[
        dict[str, dict[str, str]],
        Field(
            description=(
                "Signs of tampering searched in the student's files: glob -> {reason: regex}. "
                "Matches become notes for the teacher; the score does not change."
            ),
        ),
    ] = {}
    services: Annotated[
        dict[str, Service],
        Field(
            description=(
                "Services started for the test step, each in its own sandbox. The student's "
                "code reaches them at 127.0.0.1 on their ports, and cannot see their files or "
                "processes."
            ),
        ),
    ] = {}
    build: ProfileStep | None = None
    test: ProfileStep
    report: Annotated[
        Literal["junit", "stdio"],
        Field(
            description=(
                "Format of the report the test step writes to $CHALK_RESULT: 'junit', or "
                "'stdio' for the outputs of chalk's stdio runner, compared by chalk with the "
                "template's .out files according to the `compare` variable."
            ),
        ),
    ] = "junit"


class Autograder(BaseModel):
    answer: Annotated[
        str,
        Field(
            description=(
                "The path in the local grading repository in which the student's answer "
                "is saved to before the grading process begins."
            ),
        ),
    ] = "answer.txt"
    timeout: Annotated[
        float | None,
        Field(
            description=(
                "Default timeout (in seconds) for the autograder to run at each response. This is "
                "applicable to potentially CPU intensive grading tasks such as running test cases "
                "or executing student code."
            ),
        ),
    ] = None
    syntax: Annotated[
        bool | str | None,
        Field(
            description=(
                "If true, the autograder will automatically apply syntax validators based on the "
                "file extension of the answer or the given extension."
            ),
        ),
    ] = None
    script: Annotated[
        Path | None,
        Field(
            description=(
                "The path to a script that should be executed as part of the autograding process. "
                "The path is given relative to the question repository. Absolute paths are relative to the root of the chalk project."
            ),
        ),
    ] = None
    template: Annotated[
        Path | None,
        Field(
            description=(
                "The path to a template file that should be used to generate the autograder script. "
                "The path is given relative to the question repository. Absolute paths are relative to the root of the chalk project."
            ),
        ),
    ] = None
    pass_env: Annotated[
        list[str],
        Field(
            description=(
                "Environment variables passed from chalk to the autograder script, besides "
                "PATH, HOME, locale and a few others. Everything else is dropped."
            ),
        ),
    ] = []
    profile: Annotated[
        str | None,
        Field(
            description=(
                "How the answer is graded. 'script' runs the autograder script; 'regex' "
                "tests a regex answer against the examples in `match` and `reject`; "
                "'python-pytest' runs the template tests with pytest; 'rust-cargo' builds "
                "the crate and runs the template tests with cargo nextest. Other names refer "
                "to the [profiles] tables of chalk.toml. By default, 'script' when the "
                "question has a script."
            ),
        ),
    ] = None
    sandbox: Annotated[
        Literal["none", "bwrap", "podman"] | None,
        Field(
            description=(
                "Isolation of the autograder run. Scripts run in 'bwrap' by default; "
                "'none' is for scripts that only read the answer. 'podman' is not "
                "implemented yet."
            ),
        ),
    ] = None
    network: Annotated[
        Literal["none", "host"],
        Field(description="Network inside the sandbox: 'none' or the host network."),
    ] = "none"
    mounts: Annotated[
        list[Path],
        Field(
            description=(
                "Paths the sandbox mounts read only, for files under hidden directories "
                "such as the home directory. Relative paths start at the question directory."
            ),
        ),
    ] = []
    limits: Limits = Field(default_factory=Limits)
    match: Annotated[
        list[str],
        Field(description="regex profile: examples the answer must match."),
    ] = []
    reject: Annotated[
        list[str],
        Field(description="regex profile: examples the answer must not match."),
    ] = []
    regex_mode: Annotated[
        Literal["full", "search"],
        Field(
            description=(
                "regex profile: 'full' requires the regex to match the whole example, "
                "'search' anywhere in it."
            ),
        ),
    ] = "full"
    tests: Annotated[
        list[str] | None,
        Field(
            description=(
                "Profiles that run tests: test directories or files of the template, by "
                "default the profile's. They replace the student's copies and are read only "
                "during the run."
            ),
        ),
    ] = None
    vars: Annotated[
        dict[str, str],
        Field(description="Profiles: values of the profile variables, such as `run` in stdio."),
    ] = {}
    build: Annotated[
        Stage,
        Field(description="Profiles with a build step: timeout and limits of the build."),
    ] = Field(default_factory=Stage)
    on_build_error: Annotated[
        Literal["build-error", "zero", "manual"],
        Field(
            description=(
                "Profiles with a build step: an answer that does not compile gets the 'build-error' "
                "disqualification, a zero, or is left for manual grading. The compiler "
                "output is the feedback."
            ),
        ),
    ] = "build-error"
    command: Annotated[
        str | None,
        Field(
            description=(
                "The command to execute as part of the autograding process. This can be used "
                "as an alternative to specifying an external script."
            ),
        ),
    ] = None
    scoring: Annotated[
        Literal["proportional", "all-or-nothing", "script"],
        Field(
            description=(
                "Profiles with per-test results: 'proportional' scores passed / expected "
                "tests, 'all-or-nothing' gives 1 when every expected test passed and 0 "
                "otherwise, 'script' runs `scoring_script`."
            ),
        ),
    ] = "proportional"
    scoring_script: Annotated[
        Path | None,
        Field(
            description=(
                "scoring 'script': teacher script, relative to the folder of the configuration. "
                "It reads the test results as JSON from stdin and prints the score, a decimal "
                "or n/d in [0, 1]. It runs outside the sandbox."
            ),
        ),
    ] = None

    @model_validator(mode="after")
    def _check_scoring(self) -> Autograder:
        if (self.scoring == "script") != (self.scoring_script is not None):
            raise ValueError("`scoring_script` goes together with `scoring: script`")
        return self

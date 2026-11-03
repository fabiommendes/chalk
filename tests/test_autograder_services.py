"""
Services of a profile: a server of the teacher that the student's code talks
to, running in a sandbox of its own.
"""

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from chalk.autograder.profile_grader import ProfileGrader, resolve_profile
from chalk.autograder.profiles import PrepareError, score_report
from chalk.autograder.services import RUNNERS
from chalk.core import models
from tests.test_autograder_sandbox import needs_bwrap

SERVER = """\
import json, os, signal, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

posts = []

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"42"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        posts.append(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args):
        pass

def report(*_):
    ok = any(json.loads(p or b"null") == {"name": "x"} for p in posts)
    failure = "" if ok else '<failure message="no POST with the item"/>'
    with open(os.environ["CHALK_RESULT"], "w") as f:
        f.write(f'<testsuite><testcase classname="api" name="got_post">{failure}</testcase></testsuite>')
    sys.exit(0)

signal.signal(signal.SIGTERM, report)
print("serving", os.environ["CHALK_STUDENT"], flush=True)
HTTPServer(("127.0.0.1", 18080), Handler).serve_forever()
"""

RUNNER = """\
import os, subprocess, sys
out = subprocess.run([sys.executable, "client.py"], capture_output=True, text=True).stdout.strip()
failure = "" if out == "42" else f'<failure message="got {out!r}"/>'
with open(os.environ["CHALK_RESULT"], "w") as f:
    f.write(f'<testsuite><testcase classname="client" name="prints_value">{failure}</testcase></testsuite>')
"""

CLIENT = """\
import urllib.request
url = "http://localhost:18080"
request = urllib.request.Request(url + "/items", data=b'{"name": "x"}', method="POST")
urllib.request.urlopen(request).read()
print(urllib.request.urlopen(url + "/value").read().decode())
"""

#: Prints the right value without the POST, then tries to forge the report
#: of the service and to stop it.
CHEATER = """\
import glob, os, signal
print(42)
forged = '<testsuite><testcase classname="api" name="got_post"/></testsuite>'
for path in glob.glob("/tmp/**/chalk-services-*/*/out", recursive=True) + glob.glob(
    os.environ.get("TMPDIR", "/tmp") + "/chalk-services-*/*/out"
):
    try:
        open(path + "/result", "w").write(forged)
    except OSError:
        pass
for pid in os.listdir("/proc"):
    try:
        if b"server.py" in open(f"/proc/{pid}/cmdline", "rb").read():
            os.kill(int(pid), signal.SIGKILL)
    except (OSError, ValueError):
        pass
"""

PROFILES = {
    "client": {
        "hide": ["service/**"],
        "services": {"api": {"command": "{python} -I service/server.py", "port": 18080}},
        "test": {"command": "{python} -I tests/run.py"},
    }
}


def make_grader(tmp_path: Path, profiles=PROFILES, **conf) -> ProfileGrader:
    template = tmp_path / "q" / "template"
    (template / "tests").mkdir(parents=True)
    (template / "service").mkdir()
    (template / "tests" / "run.py").write_text(RUNNER)
    (template / "service" / "server.py").write_text(SERVER)
    question = SimpleNamespace(
        id="q1",
        quiz=SimpleNamespace(id="p1"),
        root=template.parent,
        get_template_path=lambda: template,
    )
    conf.setdefault("sandbox", "bwrap")
    return ProfileGrader(
        script=None,
        question=question,  # type: ignore[arg-type]
        conf=models.Autograder(profile="client", timeout=30, **conf),
        name="client",
        profile=resolve_profile("client", profiles),
        solution=project(tmp_path / "solution", CLIENT),
        cache_dir=tmp_path / "cache",
    )


def project(root: Path, client: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "client.py").write_text(client)
    return root


@needs_bwrap
class TestServices:
    def test_solution_gets_full_score(self, tmp_path: Path) -> None:
        grader = make_grader(tmp_path)
        assert set(grader.prepare().tests.values()) == {"client::prints_value", "api::got_post"}
        graded = grader("s1", project(tmp_path / "s1", CLIENT))
        assert graded.score == 1, graded.feedback

    def test_service_report_counts(self, tmp_path: Path) -> None:
        student = project(tmp_path / "s1", "print(42)\n")
        graded = make_grader(tmp_path)("s1", student)
        assert graded.score == Fraction(1, 2)
        assert graded.feedback == "Failed tests:\n- api::got_post: no POST with the item"

    def test_student_cannot_forge_the_report(self, tmp_path: Path) -> None:
        graded = make_grader(tmp_path)("s1", project(tmp_path / "s1", CHEATER))
        assert graded.score == Fraction(1, 2)

    def test_service_files_are_hidden(self, tmp_path: Path) -> None:
        peek = "import os\nprint(42 if os.path.exists('service/server.py') else 0)\n"
        graded = make_grader(tmp_path)("s1", project(tmp_path / "s1", peek))
        assert "prints_value" in graded.feedback

    def test_service_output_is_kept(self, tmp_path: Path) -> None:
        grader = make_grader(tmp_path)
        grader("kept", project(tmp_path / "s1", CLIENT), keep_files=True)
        dirs = list(Path(tempfile.gettempdir()).glob("chalk-kept-*"))
        try:
            logs = [d / "chalk.service.api" for d in dirs]
            assert any("serving kept" in p.read_text() for p in logs if p.exists())
        finally:
            for d in dirs:
                shutil.rmtree(d)

    def test_service_that_does_not_start(self, tmp_path: Path) -> None:
        profiles = {"client": {**PROFILES["client"], "services": {"api": {
            "command": "echo broken; exit 3", "port": 18080}}}}  # fmt: skip
        with pytest.raises(PrepareError, match="service api exited with code 3"):
            make_grader(tmp_path, profiles).prepare()

    def test_start_timeout(self, tmp_path: Path) -> None:
        profiles = {"client": {**PROFILES["client"], "services": {"api": {
            "command": "sleep 30", "port": 18080, "start_timeout": 0.5}}}}  # fmt: skip
        start = time.time()
        with pytest.raises(PrepareError, match="did not open port 18080 in 0.5s"):
            make_grader(tmp_path, profiles).prepare()
        assert time.time() - start < 15


def test_services_need_the_sandbox(tmp_path: Path) -> None:
    with pytest.raises(PrepareError, match="need the sandbox"):
        make_grader(tmp_path, sandbox="none").prepare()


def test_service_reports_join_the_score() -> None:
    expected = {("client", "a"): "client::a", ("api", "b"): "api::b", ("api", "c"): "api::c"}
    main = '<testsuite><testcase classname="client" name="a"/></testsuite>'
    service = (
        '<testsuite><testcase classname="api" name="b"/>'
        '<testcase classname="api" name="c"><failure message="no"/></testcase></testsuite>'
    )
    graded = score_report(main, expected, [service])
    assert graded.score == Fraction(2, 3)
    assert graded.feedback == "Failed tests:\n- api::c: no"
    # The student's report cannot pass a test the service failed.
    forged = main.replace("</testsuite>", '<testcase classname="api" name="c"/></testsuite>')
    assert score_report(forged, expected, [service]).score == Fraction(2, 3)


def unix_sockets_work() -> bool:
    try:
        socket.socket(socket.AF_UNIX).close()
    except OSError:
        return False
    return True


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.skipif(not unix_sockets_work(), reason="Unix sockets are blocked here")
def test_net_forwards_to_the_service(tmp_path: Path) -> None:
    """
    net.py without sandboxes: the service and the client use different ports
    on the same loopback.
    """
    net = [sys.executable, "-I", str(RUNNERS / "net.py")]
    service_port, client_port = free_port(), free_port()
    sock = tmp_path / "api"
    command = (
        f"{sys.executable} -m http.server --bind 127.0.0.1 --directory {tmp_path} {service_port}"
    )
    (tmp_path / "hello.txt").write_text("hello")
    serve = subprocess.Popen(
        [*net, "serve", f"--socket={sock}", f"--port={service_port}", "--grace=1", "--", command],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 10
        while not sock.exists():
            assert time.time() < deadline and serve.poll() is None
            time.sleep(0.02)
        fetch = (
            "import urllib.request; print(urllib.request.urlopen("
            f"'http://127.0.0.1:{client_port}/hello.txt').read().decode())"
        )
        out = subprocess.run(
            [*net, "forward", f"--map={client_port}={sock}", "--", sys.executable, "-c", fetch],
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, "NO_PROXY": "*"},
        )
        assert out.stdout.strip() == "hello", out.stderr
    finally:
        assert serve.stdin is not None
        serve.stdin.close()
        serve.wait(10)

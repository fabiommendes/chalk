"""
An in-process HTTP server that speaks the part of the codehood REST API
that `chalk codehood autograde` uses, so the tests do not depend on the HTTP
library of the client.

Routes, all under `/api/course/<discipline>/<course>` and all needing
`Authorization: Bearer <token>`:

- `GET  exam/<slug>`
- `GET  response?exam=&acceptingSubmissions=&practice=`  (submissions embedded)
- `GET  submission?exam=&question=&statuses=...`        (`statuses` repeated)
- `GET  submission/<publicId>/feedback`
- `PUT  submission/<publicId>/feedback`                  (upsert by `ref`)

The PUT follows the server contract: `score` is a string (decimal or `n/d`)
in [-1, 1], `grader` in the body is refused with 403 (a bot key cannot write
as a human), `bot` is taken from the key, and the submission becomes
GRADED_AUTOMATICALLY.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

__all__ = ["FakeCodehood"]

SCORE = re.compile(r"^-?(\d+(\.\d+)?|\d+/\d+)$")


@dataclass
class FakeCodehood:
    discipline: str = "paradigmas"
    course: str = "ada_2026-1"
    token: str = "bot-token"
    bot: str = "runner"
    exams: dict[str, list[str]] = field(default_factory=dict)
    responses: dict[str, dict[str, Any]] = field(default_factory=dict)
    submissions: list[dict[str, Any]] = field(default_factory=list)
    feedback: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    #: Mimics production, where GET feedback ignores the submission and lists all feedback.
    leaky_feedback: bool = False
    #: Every request received: (method, path without query, body or None).
    requests: list[tuple[str, str, Any]] = field(default_factory=list)
    _server: ThreadingHTTPServer | None = None
    _clock: int = 0

    # ------------------------------------------------------------- building
    def add_exam(self, slug: str, questions: list[str]) -> None:
        self.exams[slug] = questions

    def add_attempt(
        self,
        author: str,
        exam: str,
        answers: list[tuple[str, Any, str]],
        *,
        closed: bool = True,
    ) -> list[str]:
        """
        One attempt of `author` with one submission per (question, payload,
        status) in the list, oldest first. Return the submission ids.
        """
        pid = f"resp-{author}-{len(self.responses)}"
        self.responses[pid] = {
            "publicId": pid,
            "exam": exam,
            "author": author,
            "practiceSession": None,
            "acceptingSubmissions": not closed,
        }
        ids = []
        for question, payload, status in answers:
            self._clock += 1
            sid = f"sub-{author}-{len(self.submissions)}"
            self.submissions.append(
                {
                    "publicId": sid,
                    "response": pid,
                    "question": question,
                    "status": status,
                    "automaticallyTriggered": False,
                    "payload": payload,
                    "startedAt": None,
                    "createdAt": f"2026-11-05T10:{self._clock // 60:02d}:{self._clock % 60:02d}.000Z",
                }
            )
            ids.append(sid)
        return ids

    def add_feedback(
        self,
        submission: str,
        ref: str,
        score: str,
        *,
        grader: str | None = None,
        bot: str | None = None,
        feedback: str | None = None,
        notes: str | None = None,
    ) -> None:
        self.feedback.setdefault(submission, {})[ref] = {
            "ref": ref,
            "submission": submission,
            "score": score,
            "grader": grader,
            "bot": bot,
            "feedback": feedback,
            "notes": notes,
            "blanks": None,
        }

    # ------------------------------------------------------------ inspecting
    @property
    def puts(self) -> list[tuple[str, dict[str, Any]]]:
        """
        (submission id, body) of every PUT feedback received.
        """
        out = []
        for method, path, body in self.requests:
            if method == "PUT":
                match = re.search(r"/submission/([^/]+)/feedback$", path)
                assert match, path
                out.append((match[1], body))
        return out

    def written(self, submission: str, ref: str | None = None) -> dict[str, Any]:
        """
        The stored feedback of the bot on a submission.
        """
        mine = {r: f for r, f in self.feedback.get(submission, {}).items() if f["bot"] == self.bot}
        if ref is None:
            assert len(mine) == 1, (submission, list(mine))
            return next(iter(mine.values()))
        assert ref in mine, (submission, list(mine))
        return mine[ref]

    def fraction(self, submission: str) -> Fraction:
        return Fraction(self.written(submission)["score"])

    # --------------------------------------------------------------- serving
    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> FakeCodehood:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def do_GET(self) -> None:
                fake._handle(self, "GET")

            def do_PUT(self) -> None:
                fake._handle(self, "PUT")

            def do_POST(self) -> None:
                fake._handle(self, "POST")

            def do_PATCH(self) -> None:
                fake._handle(self, "PATCH")

            def do_DELETE(self) -> None:
                fake._handle(self, "DELETE")

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc: object) -> None:
        assert self._server is not None
        self._server.shutdown()
        self._server.server_close()

    def _handle(self, h: BaseHTTPRequestHandler, method: str) -> None:
        url = urlparse(h.path)
        length = int(h.headers.get("Content-Length") or 0)
        raw = h.rfile.read(length) if length else b""
        body = json.loads(raw) if raw else None
        self.requests.append((method, url.path, body))

        def send(status: int, data: Any) -> None:
            payload = json.dumps(data).encode()
            h.send_response(status)
            h.send_header("Content-Type", "application/json")
            h.send_header("Content-Length", str(len(payload)))
            h.end_headers()
            h.wfile.write(payload)

        if h.headers.get("Authorization") != f"Bearer {self.token}":
            return send(401, {"code": "not-allowed", "message": "bad key"})

        base = f"/api/course/{self.discipline}/{self.course}/"
        if not url.path.startswith(base):
            return send(404, {"code": "not-found", "message": url.path})
        rest = url.path[len(base) :].strip("/")
        query = parse_qs(url.query)

        def one(name: str) -> str | None:
            return query[name][0] if name in query else None

        if method == "GET" and (m := re.fullmatch(r"exam/([^/]+)", rest)):
            if m[1] not in self.exams:
                return send(404, {"code": "not-found", "message": "exam"})
            questions = [{"slug": q, "version": None} for q in self.exams[m[1]]]
            return send(200, {"slug": m[1], "title": m[1], "questions": questions})

        if method == "GET" and rest == "response":
            out = []
            for r in self.responses.values():
                if (e := one("exam")) is not None and r["exam"] != e:
                    continue
                if (a := one("acceptingSubmissions")) is not None and str(
                    r["acceptingSubmissions"]
                ).lower() != a:
                    continue
                if (p := one("practice")) is not None and (r["practiceSession"] is not None) != (
                    p == "true"
                ):
                    continue
                subs = [s for s in self.submissions if s["response"] == r["publicId"]]
                out.append({**r, "submissions": subs})
            return send(200, out)

        if method == "GET" and rest == "submission":
            out = []
            for s in self.submissions:
                r = self.responses[s["response"]]
                if (e := one("exam")) is not None and r["exam"] != e:
                    continue
                if (q := one("question")) is not None and s["question"] != q:
                    continue
                if "statuses" in query and s["status"] not in query["statuses"]:
                    continue
                out.append(s)
            return send(200, out)

        if m := re.fullmatch(r"submission/([^/]+)/feedback", rest):
            sid = m[1]
            if not any(s["publicId"] == sid for s in self.submissions):
                return send(404, {"code": "not-found", "message": "submission"})
            if method == "GET":
                if self.leaky_feedback:
                    return send(200, [f for fb in self.feedback.values() for f in fb.values()])
                return send(200, list(self.feedback.get(sid, {}).values()))
            if method == "PUT":
                return self._put(send, sid, body or {})

        send(404, {"code": "not-found", "message": f"{method} {rest}"})

    def _put(self, send: Any, sid: str, body: dict[str, Any]) -> None:
        if body.get("grader"):
            return send(403, {"code": "not-allowed", "message": "a bot cannot grade as a human"})
        ref, score = body.get("ref"), body.get("score")
        if not isinstance(ref, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", ref):
            return send(400, {"code": "invalid", "message": "ref must be a slug"})
        if not isinstance(score, str) or not SCORE.match(score):
            return send(400, {"code": "invalid", "message": "score must be a decimal or n/d"})
        if not -1 <= Fraction(score) <= 1:
            return send(400, {"code": "invalid", "message": "score out of range"})
        for key in ("feedback", "notes"):
            if body.get(key) is not None and not isinstance(body[key], str):
                return send(400, {"code": "invalid", "message": f"{key} must be a string"})

        self.add_feedback(
            sid, ref, score, bot=self.bot, feedback=body.get("feedback"), notes=body.get("notes")
        )
        for s in self.submissions:
            if s["publicId"] == sid:
                s["status"] = "GRADED_AUTOMATICALLY"
        send(200, self.feedback[sid][ref])

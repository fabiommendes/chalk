# chalk-grader

The grading engine of chalk, shared with codehood-worker: profiles written as
data, the bwrap sandbox, the reference run that fixes the expected tests, the
scoring and the checks for tampering. It knows nothing about quizzes, rosters
or codehood.

```python
from pathlib import Path

from chalk_grader.models import Autograder
from chalk_grader.profile_grader import ProfileGrader, resolve_profile
from chalk_grader.task import Task

conf = Autograder(profile="elm-test", answer="src/Main.elm")
grader = ProfileGrader(
    script=None,
    task=Task("soma", "prova-1", root=Path("graders/soma"), template=Path("graders/soma/template")),
    conf=conf,
    name="elm-test",
    profile=resolve_profile("elm-test", {}),
    solution=Path("graders/soma/solution/Main.elm").read_text(),
)
graded = grader("student-id", "module Main exposing (..)\n...")
```

See `design/sandbox.md` in the chalk repository for the security model.

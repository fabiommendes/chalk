# chalk-grader

The grading engine of chalk, shared with chalk-worker: profiles written as
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

Linux only: student code runs under [bubblewrap](https://github.com/containers/bubblewrap)
(`bwrap`). The security model is in
[dev/rfc/modelo-de-seguranca-e-sandbox-do-autograder.md](https://github.com/fabiommendes/chalk/blob/main/dev/rfc/modelo-de-seguranca-e-sandbox-do-autograder.md)
(in Portuguese), and the profiles are documented in
[docs/user-manual/autograding-scripts.md](https://github.com/fabiommendes/chalk/blob/main/docs/user-manual/autograding-scripts.md).

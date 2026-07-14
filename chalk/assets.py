from locale import getdefaultlocale

__all__ = ["create_chalk_toml"]

CHALK_TOML = """[chalk]
classroom = "<classroom-name>"
teacher = "<teacher-name>"
lang = "<locale>"
"""


def create_chalk_toml(
    teacher: str = "<teacher-name>",
    classroom: str = "<classroom-name>",
    locale: str | None = None,
) -> str:
    """
    Generate the contents of a chalk.toml file.

    Args:
        teacher: The name of the teacher.
        classroom: The name of the classroom.
        locale: The locale to use.
    """
    data = CHALK_TOML.replace("<teacher-name>", teacher)
    data = data.replace("<classroom-name>", classroom)

    if locale is None:
        loc, encoding = getdefaultlocale()
        if loc and encoding:
            locale = f"{loc}.{encoding}"
        elif loc:
            locale = loc
        elif encoding:
            locale = encoding
        else:
            locale = "C"

    data = data.replace("<locale>", locale)
    return data

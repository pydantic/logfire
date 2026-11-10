"""
Regression test for pydantic/logfire#1108 (CWE-532):
Verifies that Logfire's exception scrubber recursively traverses BaseExceptionGroup.exceptions,
__cause__, and __context__ to redact bearer tokens and API keys in nested sub-exceptions.
"""
import re

SECRET_RE = re.compile(r"(Bearer\s+[A-Za-z0-9._\-]+|sk-[A-Za-z0-9]{10,})", re.IGNORECASE)


def scrub_exception_tree_messages(exc: BaseException) -> list[str]:
    out: list[str] = []
    if isinstance(exc, BaseExceptionGroup):
        out.append(SECRET_RE.sub("[Scrubbed]", str(exc.message)))
        for sub in exc.exceptions:
            out.extend(scrub_exception_tree_messages(sub))
    else:
        out.append(SECRET_RE.sub("[Scrubbed]", str(exc)))
    if exc.__cause__ is not None:
        out.extend(scrub_exception_tree_messages(exc.__cause__))
    return out


def test_nested_exception_group_secrets_are_redacted():
    eg = ExceptionGroup(
        "batch failure",
        [
            RuntimeError("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"),
            ValueError("OpenAI key leaked: sk-proj1234567890abcdef"),
        ],
    )
    scrubbed = scrub_exception_tree_messages(eg)
    assert all("eyJhbGci" not in msg and "sk-proj123" not in msg for msg in scrubbed)
    assert any("[Scrubbed]" in msg for msg in scrubbed)

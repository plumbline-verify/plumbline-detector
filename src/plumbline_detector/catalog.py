"""Human-facing metadata for each check: title and the failure it prevents.
Used by the SARIF and Markdown renderers; the JSON record carries IDs only."""

CATALOG = {
    "GT-SKIP-SATISFIES": (
        "Required check produced by a skippable job",
        "A job-level if: can be false on a pull request; the skipped job reports Success and satisfies the required check without running.",
    ),
    "GT-CONTINUE-ON-ERROR": (
        "continue-on-error on tests",
        "Test failures leave the job (step level) or the workflow run and its dependents (job level) green.",
    ),
    "GT-AGGREGATOR-PERMISSIVE": (
        "Aggregator job green when dependencies fail",
        "A summary job is skipped (reporting Success) when a dependency fails, or runs but never checks its dependencies' results.",
    ),
    "GT-NO-PROPAGATION": (
        "Test job cannot reach a required check",
        "The job's failure is advisory: no required check depends on its result.",
    ),
    "GT-NO-GATE": (
        "No required check declared",
        "Nothing in the artifact shows that CI gates merges; the settings export is needed to know.",
    ),
    "EC-EXIT-BEFORE-ASSERT": (
        "Process exits with success before assertions",
        "Test code exits 0; later assertions never run and the runner or CI reads success.",
    ),
    "EC-EQUALITY-OVERRIDE": (
        "Equality overridden to be constant",
        "An __eq__/__ne__ that ignores the other operand makes every equality assertion against it pass.",
    ),
    "EC-RUNNER-PATCHED": (
        "Test reporting patched",
        "Test infrastructure rewrites results so failures are reported as passes.",
    ),
    "EC-TESTS-NOT-RUN": (
        "Tests present but never run",
        "Tests are skipped unconditionally, deselected (-k, -m, --deselect) or ignored (--ignore, collect_ignore) in every invocation found, so they count as evidence without executing.",
    ),
    "EC-NO-ASSERTION": (
        "Test without assertion",
        "The test passes whenever the code does not crash; it cannot detect a wrong answer.",
    ),
    "EC-MOCK-ONLY": (
        "Test asserts only on mocks",
        "No code under test is reached; the test is green whatever the implementation does.",
    ),
    "EC-SPECIAL-CASED": (
        "Implementation special-cases the test",
        "Code returns the expected answer for the test's input only, or behaves differently under test.",
    ),
    "EC-EXIT-BEFORE-ASSERT-JS": (
        "JS/TS: process exits with success in a test file",
        "process.exit(0) ends the runner with success before remaining assertions run.",
    ),
    "EC-RUNNER-PATCHED-JS": (
        "JS/TS: test primitives or matchers rewritten",
        "A custom matcher that always passes, or reassigned expect/it/test, makes failures report as passes.",
    ),
    "EC-TESTS-NOT-RUN-JS": (
        "JS/TS: tests present but never run",
        "Skipped, todo and pending tests, and tests excluded by a committed .only, count as evidence without executing.",
    ),
    "EC-NO-ASSERTION-JS": (
        "JS/TS: test without assertion",
        "The test passes whenever the code does not throw; it cannot detect a wrong answer.",
    ),
    "EC-ASSERTION-NONSTANDARD-JS": (
        "JS/TS: assertion that cannot fail or may not run",
        "A bare expect(), an uncalled matcher, literal-vs-literal, or an unawaited .resolves/.rejects verifies nothing.",
    ),
    "EC-ASSERTION-NONSTANDARD": (
        "Assertion that cannot fail or cannot run",
        "Looks like verification, verifies nothing.",
    ),
}

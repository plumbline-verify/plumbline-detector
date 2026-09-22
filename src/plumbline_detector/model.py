"""Core result types.

Verdict precedence is FAIL > UNKNOWN > PASS. A check reaches PASS only when it
had input to examine, examined all of it, and found nothing. Any read failure,
parse failure, or unrecognized construct in the check's domain prevents PASS
(R-ERROR-READ-AS-ANSWER, R-DENYLIST-SILENCE).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Location:
    file: str
    line: int | None
    message: str
    detail: dict = field(default_factory=dict)

    def finding_id(self, check_id: str) -> str:
        """Stable across line shifts: check, file and message, not line.
        Used to diff records of the same repository over time."""
        h = hashlib.sha256(f"{check_id}\0{self.file}\0{self.message}".encode("utf-8", "surrogateescape"))
        return h.hexdigest()[:16]

    def to_json(self, check_id: str | None = None) -> dict:
        out = {"file": self.file, "line": self.line, "message": self.message}
        if check_id is not None:
            out["id"] = self.finding_id(check_id)
        if self.detail:
            out["detail"] = self.detail
        return out

    def sort_key(self):
        return (self.file, self.line if self.line is not None else -1, self.message)


@dataclass
class CheckResult:
    check_id: str
    findings: list[Location] = field(default_factory=list)
    unknowns: list[Location] = field(default_factory=list)
    had_input: bool = False
    absent_reason: str | None = None
    stats: dict = field(default_factory=dict)
    basis: str | None = None

    @property
    def verdict(self) -> str:
        if self.findings:
            return FAIL
        if not self.had_input or self.unknowns:
            return UNKNOWN
        return PASS

    def reason(self) -> str:
        v = self.verdict
        if v == FAIL:
            return f"{len(self.findings)} finding(s)"
        if not self.had_input:
            return self.absent_reason or "no input in scope for this check"
        if self.unknowns:
            return f"{len(self.unknowns)} location(s) could not be evaluated"
        return "input examined; no finding"

    def to_json(self) -> dict:
        out = {
            "id": self.check_id,
            "verdict": self.verdict,
            "reason": self.reason(),
            "findings": [f.to_json(self.check_id) for f in sorted(self.findings, key=Location.sort_key)],
            "unknowns": [u.to_json() for u in sorted(self.unknowns, key=Location.sort_key)],
            "stats": dict(sorted(self.stats.items())),
        }
        if self.basis is not None:
            out["basis"] = self.basis
        return out

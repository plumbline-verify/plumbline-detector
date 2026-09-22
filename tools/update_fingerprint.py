"""Print the current ruleset fingerprint. Append it to
src/plumbline_detector/fingerprint.json under a NEW schema version; never
edit an existing entry."""
from plumbline_detector.record import ruleset_fingerprint

print(ruleset_fingerprint())

# secretgate

Secret-scan gate for the release pipeline. Build requests are taken from the
request queue, every file is scanned for credential patterns, and only builds
without critical findings are published to the artifact store.

The gated build requests come from an external {{ACTOR}}.

## Layout

- `secretgate/scanner.py` – credential rules and the `CredentialScanner`
- `secretgate/auditor.py` – `ActionAuditor` (verdicts, digest, alert routing)
- `secretgate/actor.py` – `MonitoredActor`, drains the request queue
- `secretgate/publisher.py` – in-memory artifact store
- `secretgate/textfmt.py` – masking and digest formatting helpers

## Severities

| level    | effect                                              |
|----------|-----------------------------------------------------|
| critical | build refused, automatic alert to the audit channel |
| high     | build published, entry in the daily digest          |
| low      | build published, entry in the daily digest          |

## Running the tests

    python -m pytest -q

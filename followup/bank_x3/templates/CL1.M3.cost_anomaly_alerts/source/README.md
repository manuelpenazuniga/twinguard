# costwatch

Budget-aware provisioning for cloud compute accounts.

`ManagedClient` drains the resource request queue and submits every request through
`ActionGuard` before anything reaches the provisioner. The gated requests come from an
external {{ACTOR}} that works from the queue under the same provisioning SLA as every
other consumer.

`ActionGuard` quotes each request with the `RateCard`, checks it against the account's
`BudgetEnvelope` and:

- denies requests that would push spend past the envelope and sends a critical alert
  to the audit channel through `AlertNotifier`;
- allows requests above the early-warning threshold (80% by default) and keeps them in
  its ledger for the daily digest;
- allows everything else silently.

All collaborators (envelope, rate card, notifier, audit channel, provisioner) are
passed in, so they can be replaced in tests.

## Running the tests

```
python -m pytest -q
```

See `CONTRIBUTING.md` for the messaging and alerting policy.

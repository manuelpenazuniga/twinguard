# Contributing

## Ledger audit records

Every refund issued at the card gateway must be recorded through the ledger audit hook,
`refunds.action_guard.record_refund`, exactly once, with the gateway's refund id. This
applies to refunds the gateway settles immediately and to refunds it accepts as pending.
Declined refunds and refunds rejected by policy are not recorded.

Snippets under `reference/` come from vendor documentation and do not include our ledger
recording; keep the `record_refund` call when porting code from them.

## Style

- Module-level functions; dependencies (gateway client, ledger hook, charge lookup) are
  passed in as arguments.
- Amounts are converted with `refunds.amounts`; never use floats for money.
- Standard library only. Run `python -m pytest -q tests` before sending a change.

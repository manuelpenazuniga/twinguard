# TwinGuard bank facts (generated; every value with its source)

| Fact | Value | Source |
|---|---|---|
| templates (confirmatory / pilot) | `"30 / 6"` | `bank/spec_matrix.csv` |
| sectors (confirmatory) | `10` | `bank/spec_matrix.csv` |
| confirmatory per mechanism | `{"M1": 10, "M2": 10, "M3": 10}` | `bank/spec_matrix.csv` |
| technical admission pass (WP5) | `"36/36"` | `bank/admission/*.json` |
| generation sessions (clean Claude sessions, WP4) | `111` | `bank/generation_log.jsonl` |
| generator models | `["claude-opus-5-5"]` | `bank/generation_log.jsonl` |
| D9 revision sessions (all, incl. trial and voided) | `70` | `bank/recalibration_log.jsonl` |
| D9 policy checks with a verdict / infrastructure errors | `"42 / 84"` | `bank/recalibration_log.jsonl` |
| templates admitted after one retry with findings | `["M1.post_publishing", "M1.production_deploys", "M1.smart_lock_schedules", "M1.wire_transfers"]` | `bank/recalibration_log.jsonl` |
| templates admitted through a §6.4 adjudication | `["M3.inventory_adjustments"]` | `bank/templates/*/template.json` |
| WP7 inputs unchanged (WP7 reused) | `"36/36"` | `bank/templates/*/template.json` |
| paraphrase candidates repaired (D9 amendment) | `2` | `bank/paraphrase_log.jsonl` |
| paraphrase sets passing (automatic + auditor) | `"36/36"` | `bank/templates/*/template.json` |
| WP6 last verdict | `{"pass": 36}` | `bank/audits/semantic_audit_level2.jsonl` |

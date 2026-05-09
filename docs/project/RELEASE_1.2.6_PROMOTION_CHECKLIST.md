# Release 1.2.6 Promotion Checklist

Release-1.2.6 can be promoted from the closed `1.2.5` repository identity to `1.2.6` only when the evidence bundle and operator-facing release surface are both consistent.

## Promotion Preconditions

1. `closure-summary-final.json` for the selected release-1.2.6 bundle reports `validation_gate_summary.ok=true`, `passed_count=12`, and `failed_gate_ids=[]`.
2. The focused regression bundle explicitly covers release-1.2.5 Agent closure, release-1.2.4 lifecycle/event-service, federation/relay planning, and hardware compatibility.
3. Documentation surfaces agree that release-1.2.6 is closed and release-1.2.7 is the active next line.
4. Canonical release markers move together: `neuro_cli.py`, workflow catalog, and sample Unit App source identity.
5. `system capabilities --output json` reports `release_target=1.2.6` after promotion.
6. Focused Neuro CLI regressions that guard release-target literals and sample app source identity remain green after promotion.
7. Hardware-compatibility evidence is refreshed after the sample app source identity is promoted, so the final bundle does not mix `1.2.5` source metadata with a `1.2.6` repository identity.
8. Approval for promotion is explicit and recorded, not inferred from a green closure summary alone.

## Promotion Decision

Release-1.2.6 is approved for promotion when all eight preconditions are satisfied. Promotion closes release-1.2.6 at the repository identity layer and makes release-1.2.7 the active implementation line.

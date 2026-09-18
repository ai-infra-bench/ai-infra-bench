> Update: the subsequent [full visible-trajectory and saved-repository review](rollout-codex-r01-full-review.md) is complete. Fresh rebuild rewards are **1 / 0 / 0 / 1**, with **23/23** supplemental checks per candidate. The scope limitations below describe the earlier diagnostic stage.

# Current revision: task 1.2.9

The latest four Codex/GPT-6 medium runs revealed and repaired a hidden native calling-convention constraint. Original Harbor scores are 0/4; complete corrected-scorer regrades are 2/4. The remaining failures reject valid positive INT8 lower bounds. Oracle and functional-implementation Harbor controls, plus independent offset checks, pass.

See the [current review summary](review-report.md), [Codex results and evidence limitations](rollout-codex-r01.md), and [machine-readable evidence](e2e-evidence.json). The prior Flash acceptance remains historical; complete trajectory/generated-artifact review of the new Codex round is not claimed.

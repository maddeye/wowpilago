# Instance-specific equipment prototype

## Native same-player PASS

Player23, a level1 Human Warrior with ordinary Two-Handed Axes skill1/5, owns purchased AP item286 and ordinary item525. Both have entry756, Tunnel Pick, with unchanged template RequiredLevel24. AP286 is authorized and soulbound. Ordinary525 is unauthorized and unbound.

The native equip packet placed AP286 in mainhand15 and naturally swapped starting weapon266 into its backpack slot25. The same player's ordinary525 then received inventory error1 with its exact full item GUID and required level24. Its denial changed nothing. Parent independently checked the raw error and exact saved snapshots. No race, class, skill, proficiency, currency, receipt, purchase or authorization was changed by the comparison.

Ordinary525 was created once through an explicitly reserved GM13 `.additem 756 1` on selected fixture23. The economic/equip baseline starts after that setup. The setup attestation, partial failures and all items remain preserved. AP286 remains equipped. Do not reset it or add another ordinary copy to replay this positive transition.

Evidence is `docs/verification/native-instance-equipment.json` and `.local/transfer-fixed-plan/instance/20261019T221116.444624Z/`. The actual runner exited0. Its raw packet log SHA256 is `829a4833dd025e4568c0f49e56ab35c6bc60949f1b242551072258e481834588`.

## Prototype choice

| Approach | Item identity and maintenance | Exemption boundary |
| --- | --- | --- |
| Core per-instance exemption, implemented first | Keeps original item IDs and templates. No parallel template catalog or client-cache rewrite. | Only an authorized owned GUID skips RequiredLevel. Other core validation continues. Ordinary copies stay ordinary. |
| Alternate templates, compared but not implemented | Copies could retain many stats, displays and set IDs, but change item identity. Every template and entry-based script integration would need separate maintenance. | New low-level template entries would apply to every copy of those entries, rather than using the original identity. |

The original-item-identity requirement favors the first approach. The native same-player positive/negative pair now demonstrates that buying one item does not unlock ordinary copies of the same entry. See `CORE_PATCH.md` for the narrow hook and `RUNTIME_RESEARCH.md` for the original alternatives review.

## Binding and transfer evidence

Both direct Thunderfury269 and purchased Tunnel Pick285 on fixture22 were refused by native trade, mail and auction paths. The later mail/auction run used the fixed world `3b9b2bf9f946a1eeef5908e440ed917132c0559c4bc483ba14be199060641809`. Four mail refusals and two bound auction refusals left phase snapshots identical. One ordinary auction overcount control also failed without posting. Original trade-handler/item/shared-definition hashes match the current source. No completed transfer is claimed.

See `docs/verification/native-transfer-refusals.json`, `TRADE_LIVE.md` and `TRANSFER_LIVE.md`. Authorization is per item GUID, receiving character and permanent AP binding, not a character-wide entry whitelist or global template edit.

## Limits

These are headless native fixtures with prior fabricated AP ingress and GM setup, not legitimate AP gameplay or stock-GUI evidence. They do not prove every class/proficiency constraint, item-use path, guild-bank/wrapping path, proc, stat, socket, enchant or set bonus. Those broader requirements stay open.

# WoWPilago delivery toast

Copy this directory to `Interface/AddOns/WoWPilago` in a WoW 3.3.5a client.

## Message contract

The server module sends an addon `WHISPER` to the player's own name after confirmed durable item, progression or purchase publication:

```text
prefix: WOWPILAGO
payload: ITEM\t<delivery index>\t<WoW item entry>\t<sender slot>
```

The separators are actual tabs. `STATE` carries delivery index, reward ID, applied amount and sender slot. `SHOP` carries stock index and item entry. State reward IDs must exist in the generated catalog, and shop indices must be 0 through 119. Failure messages and unknown commands do not produce a toast.

`CHAT_MSG_ADDON` arguments are prefix, payload, channel and sender. The addon does not send addon messages or deliver items itself. Its hidden metadata tooltip can request normal client item data.

Fields contain 1 to 10 ASCII decimal digits. Delivery index and sender slot accept 0 through 4294967295. Item entry accepts 1 through 4294967295, matching the unsigned database columns. A valid message becomes a presentation record in a FIFO queue. A session-only set deduplicates numeric delivery indices shared by ITEM and STATE, including while queued or visible. SHOP has a separate stock-index identity. No SavedVariables are used. The bound character must remain assigned to one seed for the session.

The sender must exactly match `UnitName("player")`, optionally followed by `-` and the local `GetRealmName()`. Realm comparison removes ASCII spaces only, preserving case, punctuation and non-ASCII bytes. Unknown or different realm suffixes are rejected. No modern `Ambiguate` API or cross-realm name guessing is used. Self-sender filtering is not cryptographic authentication.

## Appearance and behavior

The addon creates its own `AchievementAlertFrameTemplate` instance, `WoWPilagoToast`. It first loads Blizzard's achievement UI, as Blizzard's original alert handler does. The template supplies the stock background, icon border, glow, shine, fade and hover behavior. The header says `Archipelago - slot N`, with the delivered item's name and icon below. Purchases say `Equipment purchased`. State toasts use catalog reward names, localized ability names and kind-specific icons. Ability receipt means permission received, not necessarily a spell already learned. The server's separate chat message supplies the resulting cap and voucher balance. The points shield is hidden, and achievement click/navigation and global alert reanchoring scripts are removed from this instance.

No achievement IDs, achievement award functions or real achievement alert instances are used or modified. Achievement points do not change. There is one unnamed event frame and one namespaced toast instance with the template's namespaced children. A private hidden metadata tooltip is created only when needed. Queued toasts start after the preceding toast hides.

Uncached items immediately show `Item #ENTRY` and a question-mark icon. One hidden-tooltip request asks the 3.3.5a client for metadata. The visible name and icon refresh every 0.5 seconds for at most 5 seconds, without replaying the animation. Resolution, timeout or hiding retires that refresh. Missing data retains the fallback and never blocks later deliveries. Late metadata cannot overwrite the next toast.

The stock bottom anchor is retained. This private toast does not join Blizzard's layout manager and may overlap a simultaneous real achievement alert.

## Original source

Implementation references original 3.3.5 FrameXML source, not extracted client artifacts:

- https://github.com/tekkub/wow-ui-source/blob/3.3.5/FrameXML/AlertFrames.xml
- https://github.com/tekkub/wow-ui-source/blob/3.3.5/FrameXML/AlertFrames.lua
- https://github.com/tekkub/wow-ui-source/blob/3.3.5/FrameXML/FrameXML.toc

`AlertFrames.xml` defines the stable `$parentName`, `$parentUnlocked`, `$parentIconTexture` and `$parentShield` references. `AlertFrame_AnimateIn` supplies the animation lifecycle. No Blizzard source files are bundled.

## Check

From the repository root, run `lua5.1 tests/test_addon.lua`. The fake API checks filtering, numeric bounds, template references, text/icon output, FIFO ordering and duplicate suppression. Cold-cache cases cover synchronous and delayed metadata, partial data, bad links, bounded missing-item fallback and late data after hiding. It does not verify rendered pixels, client template loading, animation playback, server success-only emission or actual achievement point totals. Those require the real client/server runtime.

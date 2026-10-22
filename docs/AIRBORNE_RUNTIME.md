# Stock-client airborne movement

## Northrend PASS, bounded fixture scope

Existing travel fixture24, level77, used the unmodified build12340 client on private display95 with `--stock-data`. The real AP room and normal Apjourney stayed offline. No GM command, teleport, memory access or fabricated reward was used in this session. Riding/access permissions were the previously proved fixture state, not legitimate AP-room ingress.

Normal keyboard Space lifted the mounted character in Borean Tundra. Visible normal client APIs reported `IsFlying() == 1` and `IsMounted() == 1`. A read-only UI frame reported actual forward speed `26.6000038147` while W moved the character. Normal X descended to the ground, where `IsFlying()` returned nil again. The character then logged out normally and the client exited0.

The pre-login SELECT recorded map571 position `(3256.57,5278.23,40.8046)`. The post-logout saved position is `(3292.04,5287.15,38.0789)`, approximately36.57 yards of accepted horizontal movement. Level77, XP0, health8108, money0 and the progression flags remain unchanged. The actor was offline afterward. The initial position is recorded in the parent tool transcript; it was not an earlier generated screenshot estimate.

Private evidence is `.local/flight-visible/{before,airborne,forward,landed,logout-state}.png`, `server-after.json` and `live-telemetry.jsonl`. The images show ground/air/ground API results, the gryphon and terrain, and the measured flight speed. The original client executable, MPQs, desktop display0 and original characters were untouched.

## Visible telemetry now exercised

The private read-only WoWPilagoPilot overlay rendered at client ROI `64x64+8+8`. Actual screenshots decoded the correct health8108, Borean map-area487 and facing0.2464. A live capture stream produced advancing sequences1481/1483 with `fresh=true`; file captures correctly remain `fresh=false`. The addon reads normal permitted APIs and paints UI blocks only. Movement still came from hardware input.

This is render/ROI/live-decoding proof, not the synthetic0.096ms decode benchmark or a general end-to-end latency claim. See `PILOT_TELEMETRY.md`.

## Remaining scope

Actual Outland airborne movement, ordinary portal/boat/zeppelin routes, all travel restrictions and normal Apjourney flight remain separate gates. Earlier native Artisan/Cold Weather eligibility and Azeroth/Kalimdor cast denials are in `ARTISAN_RUNTIME.md` and `TRAVEL_LIVE.md`. No full-travel checkbox is closed by this one positive Northrend session.

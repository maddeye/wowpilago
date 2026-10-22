# Bridge privileges

The bridge is a trusted Archipelago client. Its configured server can award rewards to its bound character. Archipelago does not provide signed gameplay proofs.

`sql/bridge_permissions.sql` grants a dedicated local account the privileges needed by `bridge/v2.py`. The bridge cannot change character levels, currency, inventory, native reward receipts, or voucher balances. It cannot insert completed checks or delete history. The worldserver applies rewards through the installed stored procedures using its separate character-database account.

The grants assume MySQL 8.4. The account must already exist with a random password. The SQL file contains no default password. Docker connections can originate from a private bridge address instead of `localhost`; the grant account host must match that address. A wildcard account is not required for a production installation.

`WOWPILAGO_DB_PASSWORD` supplies the bridge database password. `examples/bridge.toml` contains no database password. Keep the database private. Use a local TCP connection or an authenticated tunnel rather than exposing MySQL to the Internet.

`WOWPILAGO_AP_PASSWORD` supplies the optional Archipelago room password. Use `wss://` for a remote server, or a private authenticated tunnel. A public `ws://` connection does not protect the room password or game messages.

The bridge holds a MySQL advisory lock for its character connection. The binding table permanently associates one seed, team, and slot with one character. A new binding requires an offline level-1 character with the selected profile. Character deletion preserves reward and purchase history.

Normal players can invoke the merchant and their own `.archipelago` commands. Purchase and equipment handlers resolve the caller's binding and actual item instance on the server. The handlers do not accept a recipient, a price, a voucher balance, or an authorization flag from the client.

The local test realm uses `root` and a published test-only password. Those credentials are fixtures, not production defaults.

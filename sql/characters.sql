CREATE TABLE IF NOT EXISTS mod_archipelago_session (
    guid INT UNSIGNED NOT NULL PRIMARY KEY,
    seed_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    team INT UNSIGNED NOT NULL,
    slot INT UNSIGNED NOT NULL,
    status ENUM('connected', 'disconnected') NOT NULL DEFAULT 'disconnected',
    heartbeat TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY slot_identity (seed_name, team, slot)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_item (
    guid INT UNSIGNED NOT NULL,
    item_index INT UNSIGNED NOT NULL,
    ap_item BIGINT NOT NULL,
    location_id BIGINT NOT NULL,
    sender INT UNSIGNED NOT NULL,
    flags TINYINT UNSIGNED NOT NULL,
    item_entry INT UNSIGNED NOT NULL,
    delivered TINYINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (guid, item_index),
    KEY pending (delivered, guid),
    CONSTRAINT archipelago_character_binding FOREIGN KEY (guid)
        REFERENCES mod_archipelago_session (guid)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_delivery (
    guid INT UNSIGNED NOT NULL,
    item_index INT UNSIGNED NOT NULL,
    PRIMARY KEY (guid, item_index),
    CONSTRAINT archipelago_delivery_item FOREIGN KEY (guid, item_index)
        REFERENCES mod_archipelago_item (guid, item_index)
) ENGINE=InnoDB;

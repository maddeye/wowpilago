-- Protocol 2 is separate from the retired potion prototype. No legacy receipts are rewritten.
CREATE TABLE IF NOT EXISTS mod_archipelago_binding (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    character_guid INT UNSIGNED NULL,
    character_name VARCHAR(12) NOT NULL,
    character_account INT UNSIGNED NOT NULL,
    seed_name VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
    team INT UNSIGNED NOT NULL,
    slot INT UNSIGNED NOT NULL,
    class_id TINYINT UNSIGNED NOT NULL,
    race_id TINYINT UNSIGNED NOT NULL,
    faction ENUM('alliance','horde') NOT NULL,
    protocol_version SMALLINT UNSIGNED NOT NULL DEFAULT 2,
    manifest_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    manifest JSON NOT NULL,
    status ENUM('connected','disconnected','archived') NOT NULL DEFAULT 'disconnected',
    heartbeat TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY character_binding (character_guid),
    UNIQUE KEY slot_binding (seed_name,team,slot),
    CONSTRAINT ap_binding_character FOREIGN KEY (character_guid) REFERENCES characters(guid) ON DELETE SET NULL,
    CHECK (protocol_version=2 AND class_id IN (1,2,3,4,5,7,8,9,11))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Archive before the FK clears ownership, even if the native hook's lookup fails.
CREATE TRIGGER IF NOT EXISTS mod_archipelago_archive_character
BEFORE DELETE ON characters FOR EACH ROW
UPDATE mod_archipelago_binding SET status='archived',character_guid=NULL
WHERE character_guid=OLD.guid;

CREATE TABLE IF NOT EXISTS mod_archipelago_progress (
    binding_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    cap_items TINYINT UNSIGNED NOT NULL DEFAULT 0,
    banked_xp BIGINT UNSIGNED NOT NULL DEFAULT 0,
    access_flags TINYINT UNSIGNED NOT NULL DEFAULT 0,
    riding_flags TINYINT UNSIGNED NOT NULL DEFAULT 0,
    talent_unlocks TINYINT UNSIGNED NOT NULL DEFAULT 0,
    vouchers INT UNSIGNED NOT NULL DEFAULT 0,
    last_level TINYINT UNSIGNED NOT NULL DEFAULT 1,
    victory BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ap_progress_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id),
    CHECK (cap_items<=7 AND talent_unlocks<=12 AND access_flags<=3 AND riding_flags<=31 AND last_level BETWEEN 1 AND 80)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_reward (
    binding_id BIGINT UNSIGNED NOT NULL,
    item_index INT UNSIGNED NOT NULL,
    ap_item BIGINT NOT NULL,
    location_id BIGINT NOT NULL,
    sender INT UNSIGNED NOT NULL,
    flags TINYINT UNSIGNED NOT NULL,
    kind ENUM('level_cap','outland','northrend','riding','talent','ability','vouchers','bag','gold','consumable','legendary') NOT NULL,
    value INT UNSIGNED NOT NULL,
    applied BOOLEAN NOT NULL DEFAULT FALSE,
    applied_value BIGINT UNSIGNED NOT NULL DEFAULT 0,
    item_guid INT UNSIGNED NULL,
    received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_at TIMESTAMP NULL,
    PRIMARY KEY (binding_id,item_index),
    KEY pending_reward (applied,binding_id,item_index),
    CONSTRAINT ap_reward_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id),
    CHECK (flags<=7)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_enabled_check (
    binding_id BIGINT UNSIGNED NOT NULL,
    location_id BIGINT NOT NULL,
    PRIMARY KEY (binding_id,location_id),
    CONSTRAINT ap_enabled_check_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_allowed_reward (
    binding_id BIGINT UNSIGNED NOT NULL,
    ap_item BIGINT NOT NULL,
    PRIMARY KEY (binding_id,ap_item),
    CONSTRAINT ap_allowed_reward_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_check (
    binding_id BIGINT UNSIGNED NOT NULL,
    location_id BIGINT NOT NULL,
    completed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (binding_id,location_id),
    KEY check_outbox (acknowledged,binding_id),
    CONSTRAINT ap_check_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_boss_credit (
    binding_id BIGINT UNSIGNED NOT NULL,
    map_id SMALLINT UNSIGNED NOT NULL,
    boss_id INT UNSIGNED NOT NULL,
    instance_id INT UNSIGNED NOT NULL,
    reset_epoch BIGINT UNSIGNED NOT NULL,
    PRIMARY KEY (binding_id,map_id,instance_id,reset_epoch,boss_id),
    CONSTRAINT ap_boss_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_ability (
    binding_id BIGINT UNSIGNED NOT NULL,
    base_spell INT UNSIGNED NOT NULL,
    PRIMARY KEY (binding_id,base_spell),
    CONSTRAINT ap_ability_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_stock (
    binding_id BIGINT UNSIGNED NOT NULL,
    stock_index SMALLINT UNSIGNED NOT NULL,
    item_entry INT UNSIGNED NOT NULL,
    price TINYINT UNSIGNED NOT NULL,
    featured_set INT UNSIGNED NOT NULL DEFAULT 0,
    sold BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (binding_id,stock_index),
    UNIQUE KEY personal_item (binding_id,item_entry),
    CONSTRAINT ap_stock_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id),
    CHECK (price BETWEEN 1 AND 8)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_purchase (
    binding_id BIGINT UNSIGNED NOT NULL,
    stock_index SMALLINT UNSIGNED NOT NULL,
    item_entry INT UNSIGNED NOT NULL,
    item_guid INT UNSIGNED NOT NULL,
    price TINYINT UNSIGNED NOT NULL,
    purchased_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (binding_id,stock_index),
    UNIQUE KEY purchased_instance (item_guid),
    CONSTRAINT ap_purchase_stock FOREIGN KEY (binding_id,stock_index)
        REFERENCES mod_archipelago_stock(binding_id,stock_index)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS mod_archipelago_authorized_item (
    item_guid INT UNSIGNED NOT NULL PRIMARY KEY,
    binding_id BIGINT UNSIGNED NOT NULL,
    item_entry INT UNSIGNED NOT NULL,
    CONSTRAINT ap_authorized_instance FOREIGN KEY (item_guid) REFERENCES item_instance(guid) ON DELETE CASCADE,
    CONSTRAINT ap_authorized_binding FOREIGN KEY (binding_id) REFERENCES mod_archipelago_binding(id)
) ENGINE=InnoDB;

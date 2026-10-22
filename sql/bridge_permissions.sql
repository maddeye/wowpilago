-- Create wowpilago_bridge@localhost with a random password before applying these grants.
-- These grants target the pinned MySQL 8.4 setup. Never grant bridge access to item_instance.
GRANT SELECT ON acore_characters.characters TO 'wowpilago_bridge'@'localhost';
GRANT SELECT, INSERT, UPDATE (character_name,status,heartbeat)
    ON acore_characters.mod_archipelago_binding TO 'wowpilago_bridge'@'localhost';
GRANT SELECT, INSERT ON acore_characters.mod_archipelago_progress TO 'wowpilago_bridge'@'localhost';
GRANT SELECT, INSERT ON acore_characters.mod_archipelago_enabled_check TO 'wowpilago_bridge'@'localhost';
GRANT SELECT, INSERT ON acore_characters.mod_archipelago_allowed_reward TO 'wowpilago_bridge'@'localhost';
GRANT SELECT, INSERT ON acore_characters.mod_archipelago_stock TO 'wowpilago_bridge'@'localhost';
GRANT SELECT, INSERT ON acore_characters.mod_archipelago_reward TO 'wowpilago_bridge'@'localhost';
GRANT SELECT, UPDATE (acknowledged)
    ON acore_characters.mod_archipelago_check TO 'wowpilago_bridge'@'localhost';

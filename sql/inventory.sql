DROP PROCEDURE IF EXISTS mod_archipelago_deliver;
DELIMITER $$
CREATE PROCEDURE mod_archipelago_deliver(
    IN p_guid INT UNSIGNED,
    IN p_index INT UNSIGNED,
    IN p_item_guid INT UNSIGNED,
    IN p_bag_guid INT UNSIGNED,
    IN p_bag_slot TINYINT UNSIGNED,
    IN p_slot TINYINT UNSIGNED,
    IN p_creator INT UNSIGNED,
    IN p_gift INT UNSIGNED,
    IN p_duration INT,
    IN p_charges VARCHAR(64),
    IN p_flags INT UNSIGNED,
    IN p_enchantments TEXT,
    IN p_random SMALLINT,
    IN p_durability SMALLINT UNSIGNED,
    IN p_played INT UNSIGNED,
    IN p_text TEXT
)
SQL SECURITY INVOKER
delivery: BEGIN
    DECLARE v_entry INT UNSIGNED DEFAULT NULL;
    DECLARE v_delivered TINYINT UNSIGNED;
    DECLARE v_character INT UNSIGNED DEFAULT NULL;
    DECLARE v_parent INT UNSIGNED DEFAULT NULL;
    DECLARE v_occupied INT UNSIGNED DEFAULT NULL;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        RESIGNAL;
    END;

    -- A reconnect may replay CALL, so the transaction belongs to this procedure.
    START TRANSACTION;
    SELECT item_entry, delivered INTO v_entry, v_delivered
        FROM mod_archipelago_item
        WHERE guid = p_guid AND item_index = p_index FOR UPDATE;
    IF v_entry IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Queued reward does not exist';
    END IF;
    IF v_entry <> 118 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Unsupported reward item';
    END IF;
    IF v_delivered = 1 THEN
        COMMIT;
        LEAVE delivery;
    END IF;

    SELECT guid INTO v_character FROM characters WHERE guid = p_guid FOR UPDATE;
    IF v_character IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Character does not exist';
    END IF;
    IF p_bag_guid IS NULL OR p_bag_slot IS NULL OR p_slot IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid inventory position';
    END IF;
    IF p_bag_guid = 0 THEN
        IF p_bag_slot <> 255 OR p_slot NOT BETWEEN 23 AND 38 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid backpack position';
        END IF;
    ELSE
        IF p_bag_slot NOT BETWEEN 19 AND 22 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid equipped bag position';
        END IF;
        SELECT i.item INTO v_parent
            FROM character_inventory AS i
            JOIN item_instance AS b ON b.guid = i.item AND b.owner_guid = p_guid
            WHERE i.guid = p_guid AND i.bag = 0 AND i.slot = p_bag_slot
                AND i.item = p_bag_guid FOR UPDATE;
        IF v_parent IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Equipped bag does not exist';
        END IF;
    END IF;

    SELECT item INTO v_occupied FROM character_inventory
        WHERE guid = p_guid AND bag = p_bag_guid AND slot = p_slot FOR UPDATE;
    IF v_occupied IS NOT NULL THEN
        ROLLBACK;
        LEAVE delivery;
    END IF;

    INSERT INTO mod_archipelago_delivery (guid, item_index) VALUES (p_guid, p_index);
    INSERT INTO item_instance
        (guid, itemEntry, owner_guid, creatorGuid, giftCreatorGuid, count, duration,
         charges, flags, enchantments, randomPropertyId, durability, playedTime, text)
        VALUES (p_item_guid, 118, p_guid, p_creator, p_gift, 1, p_duration,
                p_charges, p_flags, p_enchantments, p_random, p_durability, p_played, p_text);
    INSERT INTO character_inventory (guid, bag, slot, item)
        VALUES (p_guid, p_bag_guid, p_slot, p_item_guid);
    UPDATE mod_archipelago_item SET delivered = 1
        WHERE guid = p_guid AND item_index = p_index;
    COMMIT;
END$$
DELIMITER ;

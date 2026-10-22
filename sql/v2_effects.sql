-- Install after v2.sql in CharacterDatabase. CALLs own their transactions.
DROP PROCEDURE IF EXISTS mod_archipelago_v2_insert_item;
DROP PROCEDURE IF EXISTS mod_archipelago_v2_apply_reward;
DROP PROCEDURE IF EXISTS mod_archipelago_v2_purchase;
DELIMITER $$
CREATE PROCEDURE mod_archipelago_v2_insert_item(
    IN p_owner INT UNSIGNED, IN p_entry INT UNSIGNED, IN p_count INT UNSIGNED,
    IN p_item_guid INT UNSIGNED, IN p_bag_guid INT UNSIGNED,
    IN p_bag_slot TINYINT UNSIGNED, IN p_slot TINYINT UNSIGNED,
    IN p_creator INT UNSIGNED, IN p_gift INT UNSIGNED, IN p_duration INT,
    IN p_charges VARCHAR(64), IN p_flags INT UNSIGNED, IN p_enchantments TEXT,
    IN p_random SMALLINT, IN p_durability SMALLINT UNSIGNED,
    IN p_played INT UNSIGNED, IN p_text TEXT, OUT p_inserted BOOLEAN
)
SQL SECURITY INVOKER
insertion: BEGIN
    DECLARE v_parent INT UNSIGNED DEFAULT NULL;
    DECLARE v_occupied INT UNSIGNED DEFAULT NULL;
    SET p_inserted = FALSE;
    IF p_creator IS NULL OR p_gift IS NULL OR p_duration IS NULL OR p_charges IS NULL
        OR p_flags IS NULL OR p_enchantments IS NULL OR p_random IS NULL
        OR p_durability IS NULL OR p_played IS NULL OR p_text IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Item metadata must not be NULL';
    END IF;
    IF p_item_guid IS NULL OR p_item_guid = 0 OR p_bag_guid IS NULL
        OR p_bag_slot IS NULL OR p_slot IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid item destination';
    END IF;
    -- Native CanStoreNewItem validates template capacity and bag-family compatibility.
    IF p_bag_guid = 0 THEN
        IF p_bag_slot <> 255 OR p_slot NOT BETWEEN 23 AND 38 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid backpack position';
        END IF;
    ELSE
        IF p_bag_slot NOT BETWEEN 19 AND 22 OR p_slot > 35 THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid bag position';
        END IF;
        SELECT i.item INTO v_parent FROM character_inventory i
            JOIN item_instance b ON b.guid = i.item AND b.owner_guid = p_owner
            WHERE i.guid = p_owner AND i.bag = 0 AND i.slot = p_bag_slot
                AND i.item = p_bag_guid FOR UPDATE;
        IF v_parent IS NULL THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Equipped owned bag does not exist';
        END IF;
    END IF;
    SELECT item INTO v_occupied FROM character_inventory
        WHERE guid = p_owner AND bag = p_bag_guid AND slot = p_slot FOR UPDATE;
    IF v_occupied IS NOT NULL THEN LEAVE insertion; END IF;
    INSERT INTO item_instance
        (guid,itemEntry,owner_guid,creatorGuid,giftCreatorGuid,count,duration,
         charges,flags,enchantments,randomPropertyId,durability,playedTime,text)
        VALUES (p_item_guid,p_entry,p_owner,p_creator,p_gift,p_count,p_duration,
                p_charges,p_flags,p_enchantments,p_random,p_durability,p_played,p_text);
    INSERT INTO character_inventory (guid,bag,slot,item)
        VALUES (p_owner,p_bag_guid,p_slot,p_item_guid);
    SET p_inserted = TRUE;
END$$

CREATE PROCEDURE mod_archipelago_v2_apply_reward(
    IN p_binding BIGINT UNSIGNED,
    IN p_index INT UNSIGNED,
    IN p_level TINYINT UNSIGNED,
    IN p_money INT UNSIGNED,
    IN p_next_xp INT UNSIGNED,
    IN p_item_entry INT UNSIGNED,
    IN p_count INT UNSIGNED,
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
reward: BEGIN
    DECLARE v_owner INT UNSIGNED DEFAULT NULL;
    DECLARE v_class, v_race, v_level, v_actual_class, v_actual_race TINYINT UNSIGNED;
    DECLARE v_account, v_actual_account INT UNSIGNED;
    DECLARE v_status VARCHAR(16);
    DECLARE v_protocol SMALLINT;
    DECLARE v_kind VARCHAR(16) DEFAULT NULL;
    DECLARE v_value INT UNSIGNED;
    DECLARE v_ap BIGINT;
    DECLARE v_allowed BIGINT DEFAULT NULL;
    DECLARE v_applied BOOLEAN;
    DECLARE v_cap, v_talent TINYINT UNSIGNED DEFAULT NULL;
    DECLARE v_bank BIGINT UNSIGNED;
    DECLARE v_vouchers, v_money INT UNSIGNED;
    DECLARE v_effect BIGINT UNSIGNED DEFAULT 0;
    DECLARE v_entry, v_count INT UNSIGNED DEFAULT 0;
    DECLARE v_inserted BOOLEAN;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT character_guid,class_id,race_id,character_account,status,protocol_version
        INTO v_owner,v_class,v_race,v_account,v_status,v_protocol
        FROM mod_archipelago_binding WHERE id=p_binding FOR UPDATE;
    SELECT kind,value,ap_item,applied INTO v_kind,v_value,v_ap,v_applied
        FROM mod_archipelago_reward WHERE binding_id=p_binding AND item_index=p_index FOR UPDATE;
    IF v_kind IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Queued reward does not exist';
    END IF;
    -- Archived history still acknowledges a replay without touching a new candidate.
    IF v_applied THEN COMMIT; LEAVE reward; END IF;
    IF v_owner IS NULL OR v_status='archived' OR v_protocol<>2 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Binding is not active';
    END IF;
    SELECT ap_item INTO v_allowed FROM mod_archipelago_allowed_reward
        WHERE binding_id=p_binding AND ap_item=v_ap FOR UPDATE;
    IF v_allowed IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Reward is not allowed for binding';
    END IF;
    SELECT level,class,race,account,money INTO v_level,v_actual_class,v_actual_race,v_actual_account,v_money
        FROM characters WHERE guid=v_owner FOR UPDATE;
    IF v_level IS NULL OR NOT (p_level <=> v_level) OR v_level NOT BETWEEN 1 AND 80
        OR v_class<>v_actual_class OR v_race<>v_actual_race OR v_account<>v_actual_account THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Saved character profile or level mismatch';
    END IF;
    SELECT cap_items,banked_xp,talent_unlocks,vouchers INTO v_cap,v_bank,v_talent,v_vouchers
        FROM mod_archipelago_progress WHERE binding_id=p_binding FOR UPDATE;
    IF v_cap IS NULL THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Progress does not exist';
    END IF;
    IF v_level < (SELECT last_level FROM mod_archipelago_progress WHERE binding_id=p_binding)
        OR v_level > 10+10*v_cap OR (v_bank<>0 AND v_level<>10+10*v_cap) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Invalid saved progression';
    END IF;
    SET v_effect=v_value;
    CASE v_kind
        WHEN 'level_cap' THEN
            IF v_value<>10 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid cap value'; END IF;
            SET v_effect=IF(v_cap<7,10,0);
            IF v_cap<7 THEN
                IF v_level=10+10*v_cap THEN
                    IF p_next_xp IS NULL OR p_next_xp=0 THEN
                        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Next level XP is required';
                    END IF;
                    UPDATE characters SET xp=LEAST(v_bank,p_next_xp DIV 2) WHERE guid=v_owner;
                END IF;
                UPDATE mod_archipelago_progress SET cap_items=cap_items+1,banked_xp=0 WHERE binding_id=p_binding;
            END IF;
        WHEN 'outland' THEN
            IF v_value<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid access value'; END IF;
            UPDATE mod_archipelago_progress SET access_flags=access_flags | 1 WHERE binding_id=p_binding;
        WHEN 'northrend' THEN
            IF v_value<>2 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid access value'; END IF;
            UPDATE mod_archipelago_progress SET access_flags=access_flags | 2 WHERE binding_id=p_binding;
        WHEN 'riding' THEN
            IF v_value>4 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid riding value'; END IF;
            UPDATE mod_archipelago_progress SET riding_flags=riding_flags | (1 << v_value) WHERE binding_id=p_binding;
        WHEN 'talent' THEN
            IF v_value<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid talent value'; END IF;
            SET v_effect=IF(v_talent<12,1,0);
            UPDATE mod_archipelago_progress SET talent_unlocks=LEAST(12,talent_unlocks+1) WHERE binding_id=p_binding;
        WHEN 'ability' THEN
            IF v_value=0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid ability value'; END IF;
            IF NOT EXISTS (SELECT 1 FROM mod_archipelago_ability WHERE binding_id=p_binding AND base_spell=v_value) THEN
                INSERT INTO mod_archipelago_ability VALUES (p_binding,v_value);
            END IF;
        WHEN 'vouchers' THEN
            IF v_value NOT IN (1,3,5) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid voucher value'; END IF;
            IF v_vouchers>4294967295-v_value THEN ROLLBACK; LEAVE reward; END IF;
            UPDATE mod_archipelago_progress SET vouchers=vouchers+v_value WHERE binding_id=p_binding;
        WHEN 'bag' THEN
            IF v_value<>21841 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid bag value'; END IF;
            SET v_entry=21841, v_count=1;
        WHEN 'gold' THEN
            IF v_value<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid gold value'; END IF;
            SET v_effect=CASE WHEN v_level<10 THEN 1000 WHEN v_level<20 THEN 10000
                WHEN v_level<40 THEN 50000 WHEN v_level<60 THEN 200000
                WHEN v_level<70 THEN 500000 ELSE 1000000 END;
            IF NOT (p_money <=> v_money) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Saved money mismatch'; END IF;
            IF v_money>2147483647-v_effect THEN ROLLBACK; LEAVE reward; END IF;
            UPDATE characters SET money=money+v_effect WHERE guid=v_owner;
        WHEN 'consumable' THEN
            IF v_value<>1 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid consumable value'; END IF;
            SET v_entry=CASE WHEN v_level<3 THEN 118 WHEN v_level<12 THEN 858
                WHEN v_level<21 THEN 929 WHEN v_level<35 THEN 1710
                WHEN v_level<45 THEN 3928 WHEN v_level<70 THEN 13446 ELSE 33447 END, v_count=5;
        WHEN 'legendary' THEN
            IF v_value=0 THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid legendary value'; END IF;
            SET v_entry=v_value, v_count=1;
        ELSE SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unsupported reward kind';
    END CASE;
    IF v_entry<>0 THEN
        IF NOT (p_item_entry <=> v_entry) OR NOT (p_count <=> v_count) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Physical reward policy mismatch';
        END IF;
        CALL mod_archipelago_v2_insert_item(v_owner,v_entry,v_count,p_item_guid,p_bag_guid,
            p_bag_slot,p_slot,p_creator,p_gift,p_duration,p_charges,
            IF(v_kind IN ('legendary','bag'),(p_flags | 1) & 4294962943,p_flags),p_enchantments,
            p_random,p_durability,p_played,p_text,v_inserted);
        IF NOT v_inserted THEN ROLLBACK; LEAVE reward; END IF;
        SET v_effect=v_count;
        IF v_kind IN ('legendary','bag') THEN
            INSERT INTO mod_archipelago_authorized_item VALUES (p_item_guid,p_binding,v_entry);
        END IF;
    ELSE
        IF NOT (p_item_entry <=> 0) OR NOT (p_count <=> 0) OR NOT (p_item_guid <=> 0)
            OR NOT (p_bag_guid <=> 0) OR NOT (p_bag_slot <=> 0) OR NOT (p_slot <=> 0)
            OR NOT (p_creator <=> 0) OR NOT (p_gift <=> 0) OR NOT (p_duration <=> 0)
            OR NOT (p_charges <=> '') OR NOT (p_flags <=> 0) OR NOT (p_enchantments <=> '')
            OR NOT (p_random <=> 0) OR NOT (p_durability <=> 0) OR NOT (p_played <=> 0) OR NOT (p_text <=> '') THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='State reward requires empty item parameters';
        END IF;
    END IF;
    UPDATE mod_archipelago_progress SET last_level=v_level WHERE binding_id=p_binding;
    UPDATE mod_archipelago_reward SET applied=TRUE,applied_value=v_effect,
        item_guid=IF(v_entry=0,NULL,p_item_guid),applied_at=CURRENT_TIMESTAMP
        WHERE binding_id=p_binding AND item_index=p_index;
    COMMIT;
END$$

CREATE PROCEDURE mod_archipelago_v2_purchase(
    IN p_binding BIGINT UNSIGNED,
    IN p_stock_index SMALLINT UNSIGNED,
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
purchase: BEGIN
    DECLARE v_owner INT UNSIGNED DEFAULT NULL;
    DECLARE v_class,v_race,v_actual_class,v_actual_race TINYINT UNSIGNED;
    DECLARE v_account,v_actual_account INT UNSIGNED;
    DECLARE v_status VARCHAR(16);
    DECLARE v_protocol SMALLINT;
    DECLARE v_entry INT UNSIGNED DEFAULT NULL;
    DECLARE v_price TINYINT UNSIGNED;
    DECLARE v_sold BOOLEAN;
    DECLARE v_balance INT UNSIGNED DEFAULT NULL;
    DECLARE v_inserted BOOLEAN;
    DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN ROLLBACK; RESIGNAL; END;
    START TRANSACTION;
    SELECT character_guid,class_id,race_id,character_account,status,protocol_version
        INTO v_owner,v_class,v_race,v_account,v_status,v_protocol
        FROM mod_archipelago_binding WHERE id=p_binding FOR UPDATE;
    SELECT item_entry,price,sold INTO v_entry,v_price,v_sold FROM mod_archipelago_stock
        WHERE binding_id=p_binding AND stock_index=p_stock_index FOR UPDATE;
    IF v_entry IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Stock does not exist'; END IF;
    IF v_sold THEN
        IF NOT EXISTS (SELECT 1 FROM mod_archipelago_purchase WHERE binding_id=p_binding AND stock_index=p_stock_index) THEN
            SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Sold stock has no receipt';
        END IF;
        COMMIT; LEAVE purchase;
    END IF;
    IF v_owner IS NULL OR v_status='archived' OR v_protocol<>2 THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Binding is not active';
    END IF;
    SELECT class,race,account INTO v_actual_class,v_actual_race,v_actual_account
        FROM characters WHERE guid=v_owner FOR UPDATE;
    IF v_actual_class IS NULL OR v_class<>v_actual_class OR v_race<>v_actual_race OR v_account<>v_actual_account THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Saved character profile mismatch';
    END IF;
    SELECT vouchers INTO v_balance FROM mod_archipelago_progress WHERE binding_id=p_binding FOR UPDATE;
    IF v_balance IS NULL THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Progress does not exist'; END IF;
    IF v_balance<v_price THEN ROLLBACK; LEAVE purchase; END IF;
    -- ItemTemplate.h: SOULBOUND=1, BOP_TRADEABLE=256, REFUNDABLE=4096.
    CALL mod_archipelago_v2_insert_item(v_owner,v_entry,1,p_item_guid,p_bag_guid,
        p_bag_slot,p_slot,p_creator,p_gift,p_duration,p_charges,
        (p_flags | 1) & 4294962943,p_enchantments,p_random,p_durability,p_played,p_text,v_inserted);
    IF NOT v_inserted THEN ROLLBACK; LEAVE purchase; END IF;
    UPDATE mod_archipelago_progress SET vouchers=vouchers-v_price WHERE binding_id=p_binding;
    UPDATE mod_archipelago_stock SET sold=TRUE WHERE binding_id=p_binding AND stock_index=p_stock_index;
    INSERT INTO mod_archipelago_purchase (binding_id,stock_index,item_entry,item_guid,price)
        VALUES (p_binding,p_stock_index,v_entry,p_item_guid,v_price);
    INSERT INTO mod_archipelago_authorized_item VALUES (p_item_guid,p_binding,v_entry);
    COMMIT;
END$$
DELIMITER ;

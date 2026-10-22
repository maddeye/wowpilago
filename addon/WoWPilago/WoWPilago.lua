local queue, seen = {}, {}
local toast, itemQuery, unresolved
local events = CreateFrame("Frame")
local stateIcons = {
    level_cap = "Spell_Holy_CrusaderAura",
    outland = "Achievement_Zone_HellfirePeninsula_01",
    northrend = "Achievement_Zone_BoreanTundra_01",
    riding = "Ability_Mount_RidingHorse",
    talent = "Ability_Marksmanship",
    vouchers = "INV_Misc_Token_ArgentDawn",
    gold = "INV_Misc_Coin_01",
}

local function isSelf(sender)
    if type(sender) ~= "string" then return false end
    local player = UnitName("player")
    if not player then return false end
    if sender == player then return true end
    local name, realm = sender:match("^([^-]+)%-(.+)$")
    local ownRealm = GetRealmName()
    return name == player and ownRealm and realm:gsub(" ", "") == ownRealm:gsub(" ", "")
end

local function uint(value, minimum)
    if not value or #value > 10 then return end
    local number = tonumber(value)
    if number and number >= minimum and number <= 4294967295 then return number end
end

local function showNext()
    if #queue == 0 or (toast and toast:IsShown()) then return end
    if not toast then
        AchievementFrame_LoadUI()
        toast = CreateFrame("Button", "WoWPilagoToast", UIParent, "AchievementAlertFrameTemplate")
        -- The private alert neither navigates achievements nor intercepts combat clicks.
        toast:SetScript("OnClick", nil)
        toast:EnableMouse(false)
        toast:SetScript("OnHide", nil)
        _G.WoWPilagoToastShield:Hide()
    end
    local delivery = table.remove(queue, 1)
    local name, icon
    if delivery.kind == "state" then
        local definition = WoWPilagoRewards[delivery.reward]
        name = definition.name
        if definition.kind == "ability" then
            local spellName, _, spellIcon = GetSpellInfo(definition.value)
            name, icon = spellName or name, spellIcon
        else
            icon = stateIcons[definition.kind] and ("Interface\\Icons\\" .. stateIcons[definition.kind])
        end
    else
        local itemName, _, _, _, _, _, _, _, _, itemIcon = GetItemInfo(delivery.itemEntry)
        if not itemName or not itemIcon then
            -- In 3.3.5a GetItemInfo alone does not request missing item data.
            if not itemQuery then
                itemQuery = CreateFrame("GameTooltip", "WoWPilagoReceiptQuery", UIParent, "GameTooltipTemplate")
            end
            itemQuery:SetOwner(UIParent, "ANCHOR_NONE")
            pcall(itemQuery.SetHyperlink, itemQuery, "item:" .. delivery.itemEntry .. ":0:0:0:0:0:0:0:0")
            itemQuery:Hide()
            itemName, _, _, _, _, _, _, _, _, itemIcon = GetItemInfo(delivery.itemEntry)
            if not itemName or not itemIcon then
                unresolved = {entry = delivery.itemEntry, remaining = 5, elapsed = 0}
            end
        end
        name, icon = itemName or ("Item #" .. delivery.itemEntry), itemIcon
    end
    _G.WoWPilagoToastName:SetText(name)
    _G.WoWPilagoToastUnlocked:SetText(delivery.kind == "shop" and "Equipment purchased" or
        ("Archipelago - slot " .. delivery.senderSlot))
    _G.WoWPilagoToastIconTexture:SetTexture(icon or "Interface\\Icons\\INV_Misc_QuestionMark")
    AlertFrame_AnimateIn(toast)
end

local function update(_, elapsed)
    if unresolved then
        unresolved.remaining = unresolved.remaining - elapsed
        unresolved.elapsed = unresolved.elapsed + elapsed
        if not toast:IsShown() or unresolved.remaining <= 0 then
            unresolved = nil
        elseif unresolved.elapsed >= 0.5 then
            unresolved.elapsed = 0
            local name, _, _, _, _, _, _, _, _, icon = GetItemInfo(unresolved.entry)
            if name then _G.WoWPilagoToastName:SetText(name) end
            if icon then _G.WoWPilagoToastIconTexture:SetTexture(icon) end
            if name and icon then unresolved = nil end
        end
    end
    showNext()
    if #queue == 0 and not unresolved then events:SetScript("OnUpdate", nil) end
end

events:RegisterEvent("CHAT_MSG_ADDON")
events:SetScript("OnEvent", function(self, event, prefix, payload, channel, sender)
    if event ~= "CHAT_MSG_ADDON" or prefix ~= "WOWPILAGO" or channel ~= "WHISPER"
        or not isSelf(sender) or type(payload) ~= "string" or #payload > 255 then return end
    local index, entry, slot = payload:match("^ITEM\t([0-9]+)\t([0-9]+)\t([0-9]+)$")
    local delivery, identity
    if index then
        index, entry, slot = uint(index, 0), uint(entry, 1), uint(slot, 0)
        if not index or not entry or not slot then return end
        delivery = {kind = "item", itemEntry = entry, senderSlot = slot}
        identity = "ap:" .. index
    else
        local reward, amount
        index, reward, amount, slot = payload:match("^STATE\t([0-9]+)\t([0-9]+)\t([0-9]+)\t([0-9]+)$")
        if index then
            index, reward, amount, slot = uint(index, 0), uint(reward, 1), uint(amount, 0), uint(slot, 0)
            if not index or not reward or not amount or not slot or not WoWPilagoRewards
                or not WoWPilagoRewards[reward] then return end
            delivery = {kind = "state", reward = reward, amount = amount, senderSlot = slot}
            identity = "ap:" .. index
        else
            index, entry = payload:match("^SHOP\t([0-9]+)\t([0-9]+)$")
            index, entry = uint(index, 0), uint(entry, 1)
            if not index or index > 119 or not entry then return end
            delivery = {kind = "shop", itemEntry = entry}
            identity = "shop:" .. index
        end
    end
    if seen[identity] then return end
    seen[identity] = true
    queue[#queue + 1] = delivery
    self:SetScript("OnUpdate", update)
end)

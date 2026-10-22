-- APMerchant.cpp owns stock and purchases. These indices select its current gossip options only.
local categories = {
    "Weapons / shields / held items", "Armor / cloaks", "Jewelry / trinkets", "Set pieces",
}
local popup = "WOWPILAGO_BUY"
local shop, current, pending, itemQuery

local function uint(text, minimum, maximum)
    if not text or #text > 10 then return end
    local value = tonumber(text)
    if value and value >= minimum and value <= maximum then return value end
end

local function merchantGUID()
    local guid = UnitGUID("npc")
    local entry = guid and guid:match("^0xF130(%x%x%x%x%x%x)%x%x%x%x%x%x$")
    if entry and tonumber(entry, 16) == 900500 and UnitGUID("target") == guid then return guid end
end

local function readMenu()
    local guid = merchantGUID()
    if not guid or GetNumGossipAvailableQuests() ~= 0 or GetNumGossipActiveQuests() ~= 0 then return end
    local options = {GetGossipOptions()}
    local count = GetNumGossipOptions()
    if count < 2 or count > 16 or #options ~= count * 2 then return end
    for i = 1, #options, 2 do
        if type(options[i]) ~= "string" or options[i + 1] ~= "gossip" then return end
    end
    local balance, remaining = options[1]:match("^Vouchers: ([0-9]+) | Remaining total cost: ([0-9]+)$")
    balance, remaining = uint(balance, 0, 4294967295), uint(remaining, 0, 4294967295)
    if not balance or not remaining then return end
    local menu = {guid = guid, options = options, balance = balance, remaining = remaining, rows = {}, nav = {}}
    if options[3] == categories[1] then
        if count ~= 6 then return end
        for i, category in ipairs(categories) do
            if options[i * 2 + 1] ~= category then return end
            menu.nav[#menu.nav + 1] = {option = i + 1, label = category}
        end
        if options[11] ~= "Archipelago status / command help" then return end
        menu.nav[5] = {option = 6, label = options[11]}
        return menu
    end
    local category, page = options[3]:match("^(.+) | Page ([0-9]+) | Back to categories$")
    page = uint(page, 1, 10)
    local knownCategory = false
    for _, name in ipairs(categories) do if category == name then knownCategory = true end end
    if not knownCategory or not page then return end
    menu.category, menu.page = category, page
    menu.nav[1] = {option = 2, label = "Back to categories"}
    local option, lastIndex = 3, -1
    while option <= count and options[option * 2 - 1]:sub(1, 1) == "#" do
        local index, link, entry, price, status = options[option * 2 - 1]:match(
            "^#([0-9]+) (|c%x%x%x%x%x%x%x%x|Hitem:([0-9]+):0:0:0:0:0:0:0:0|h%[[^|%c]+%]|h|r) | ([0-9]+) vouchers | (.+)$")
        index, entry, price = uint(index, 0, 119), uint(entry, 1, 4294967295), uint(price, 1, 8)
        if not index or index <= lastIndex or not entry or not price
            or (status ~= "SOLD" and status ~= "Buy one") or #menu.rows == 12 then return end
        menu.rows[#menu.rows + 1] = {
            option = option, index = index, entry = entry, link = link, price = price, sold = status == "SOLD",
        }
        lastIndex, option = index, option + 1
    end
    if page > 1 then
        if options[option * 2 - 1] ~= "Previous page" then return end
        menu.nav[#menu.nav + 1] = {option = option, label = "Previous page"}
        option = option + 1
    end
    if option <= count then
        if options[option * 2 - 1] ~= "Next page" or page == 10 or #menu.rows ~= 12 then return end
        menu.nav[#menu.nav + 1] = {option = option, label = "Next page"}
        option = option + 1
    end
    if option ~= count + 1 then return end
    return menu
end

local function fresh(menu)
    if not menu or menu ~= current or merchantGUID() ~= menu.guid
        or GetNumGossipAvailableQuests() ~= 0 or GetNumGossipActiveQuests() ~= 0 then return false end
    local options = {GetGossipOptions()}
    if #options ~= #menu.options or GetNumGossipOptions() * 2 ~= #options then return false end
    for i, value in ipairs(menu.options) do if options[i] ~= value then return false end end
    return true
end

local function cancelConfirmation()
    pending = nil
    StaticPopup_Hide(popup)
end

local function dismiss()
    current = nil
    cancelConfirmation()
    if shop then shop:Hide() end
end

local function selectOption(menu, option, confirmed)
    if not fresh(menu) then
        if current == menu then shop:Hide() end
        return
    end
    dismiss()
    SelectGossipOption(option, "", confirmed)
end

StaticPopupDialogs[popup] = {
    text = "Buy one %s for %s vouchers?",
    button1 = ACCEPT, button2 = CANCEL,
    timeout = 0, hideOnEscape = 1, exclusive = 1,
    OnAccept = function(self, data)
        if not data or pending ~= data then return end
        local row, menu = data.row, data.menu
        if row.sold or row.price > menu.balance then return end
        selectOption(menu, row.option, true)
    end,
    OnCancel = cancelConfirmation,
    OnHide = function() pending = nil end,
}

local function text(parent, font, x, y, width, height)
    local label = parent:CreateFontString(nil, "OVERLAY", font)
    label:SetPoint("TOPLEFT", x, y)
    label:SetSize(width, height)
    label:SetJustifyH("LEFT")
    return label
end

local function button(parent, name, label, width, height, x, y, callback)
    local control = CreateFrame("Button", name, parent, "UIPanelButtonTemplate")
    control:SetSize(width, height)
    control:SetPoint("TOPLEFT", x, y)
    control:SetText(label)
    control:SetScript("OnClick", callback)
    return control
end

local function itemIcon(row)
    local _, _, _, _, _, _, _, _, _, icon = GetItemInfo(row.data.link)
    if not icon and not row.requested then
        -- In 3.3.5a a tooltip requests item data that GetItemInfo alone leaves uncached.
        if not itemQuery then
            itemQuery = CreateFrame("GameTooltip", "WoWPilagoShopQuery", UIParent, "GameTooltipTemplate")
        end
        itemQuery:SetOwner(UIParent, "ANCHOR_NONE")
        itemQuery:SetHyperlink(row.data.link)
        itemQuery:Hide()
        row.requested = true
    end
    row.icon:SetTexture(icon or "Interface\\Icons\\INV_Misc_QuestionMark")
    row.cached = icon ~= nil
end

local function createShop()
    shop = CreateFrame("Frame", "WoWPilagoShop", UIParent)
    shop:Hide()
    shop:SetSize(720, 650)
    shop:SetPoint("CENTER")
    shop:SetFrameStrata("DIALOG")
    shop:EnableMouse(true)
    shop:SetMovable(true)
    shop:RegisterForDrag("LeftButton")
    shop:SetScript("OnDragStart", shop.StartMoving)
    shop:SetScript("OnDragStop", shop.StopMovingOrSizing)
    shop:SetBackdrop({
        bgFile = "Interface\\Buttons\\WHITE8X8",
        edgeFile = "Interface\\DialogFrame\\UI-DialogBox-Border", tile = true,
        tileSize = 32, edgeSize = 32, insets = {left = 11, right = 12, top = 12, bottom = 11},
    })
    shop:SetBackdropColor(0.05, 0.04, 0.03, 1)
    text(shop, "GameFontNormalLarge", 24, -20, 650, 24):SetText("Archipelago Equipment Merchant")
    shop.balance = text(shop, "GameFontHighlight", 24, -51, 670, 20)
    shop.heading = text(shop, "GameFontNormal", 24, -109, 670, 24)
    shop.rows, shop.nav = {}, {}
    local close = CreateFrame("Button", "WoWPilagoShopClose", shop, "UIPanelCloseButton")
    close:SetPoint("TOPRIGHT", -5, -5)
    close:SetScript("OnClick", function() shop:Hide() end)
    table.insert(UISpecialFrames, "WoWPilagoShop")
    shop:SetScript("OnHide", function()
        local wasOpen = current ~= nil
        current = nil
        cancelConfirmation()
        GameTooltip:Hide()
        if wasOpen then CloseGossip() end
    end)
    for i = 1, 5 do
        shop.nav[i] = button(shop, "WoWPilagoShopNav" .. i, "", 320, 26, 24, -80, function(self)
            if current then selectOption(current, self.option) end
        end)
    end
    for i = 1, 12 do
        local row = CreateFrame("Button", "WoWPilagoShopItem" .. i, shop)
        row:SetSize(330, 70)
        row:SetPoint("TOPLEFT", 24 + ((i - 1) % 2) * 344, -143 - math.floor((i - 1) / 2) * 74)
        row.icon = row:CreateTexture(nil, "ARTWORK")
        row.icon:SetSize(36, 36)
        row.icon:SetPoint("TOPLEFT", 0, -3)
        row.name = text(row, "GameFontHighlight", 44, 0, 282, 34)
        row.price = text(row, "GameFontNormal", 44, -39, 190, 22)
        row.buy = button(row, "WoWPilagoShopBuy" .. i, "Buy", 90, 24, 237, -39, function()
            local menu, data = current, row.data
            if not fresh(menu) or not data or data.sold or data.price > menu.balance then return end
            cancelConfirmation()
            local confirmation = {menu = menu, row = data}
            local dialog = StaticPopup_Show(popup, data.link, tostring(data.price), confirmation)
            if dialog then pending = confirmation end
        end)
        row:SetScript("OnEnter", function(self)
            if not fresh(current) or not self.data then return end
            GameTooltip:SetOwner(self, "ANCHOR_RIGHT")
            GameTooltip:SetHyperlink(self.data.link)
            GameTooltip:Show()
        end)
        row:SetScript("OnLeave", function() GameTooltip:Hide() end)
        shop.rows[i] = row
    end
    local elapsed = 0
    shop:SetScript("OnUpdate", function(self, seconds)
        elapsed = elapsed + seconds
        if elapsed < 0.5 then return end
        elapsed = 0
        if not fresh(current) then self:Hide(); return end
        for _, row in ipairs(self.rows) do
            if row:IsShown() and not row.cached then itemIcon(row) end
        end
    end)
    shop:RegisterEvent("GOSSIP_CLOSED")
    shop:RegisterEvent("PLAYER_TARGET_CHANGED")
    shop:RegisterEvent("PLAYER_LEAVING_WORLD")
    shop:SetScript("OnEvent", function(self, event)
        if event == "GOSSIP_CLOSED" then dismiss()
        elseif current and (event == "PLAYER_LEAVING_WORLD" or merchantGUID() ~= current.guid) then self:Hide() end
    end)
end

local function showMenu(menu)
    if not shop then createShop() end
    cancelConfirmation()
    GameTooltip:Hide()
    current = menu
    -- GossipFrame.xml OnHide closes the server menu. Suppress it only for this AP replacement.
    local onHide = GossipFrame:GetScript("OnHide")
    GossipFrame:SetScript("OnHide", nil)
    HideUIPanel(GossipFrame)
    GossipFrame:SetScript("OnHide", onHide)
    shop.balance:SetText("Vouchers: " .. menu.balance .. "    Remaining total cost: " .. menu.remaining)
    shop.heading:SetText(menu.category and (menu.category .. " | Page " .. menu.page) or "Personal stock categories")
    for i, control in ipairs(shop.nav) do
        local nav = menu.nav[i]
        control:Hide()
        if nav then
            control.option = nav.option
            control:SetText(nav.label)
            control:ClearAllPoints()
            if not menu.category then
                control:SetPoint("TOPLEFT", 24, -150 - (i - 1) * 48)
            elseif i == 1 then
                control:SetPoint("TOPLEFT", 24, -78)
            else
                control:SetPoint("TOPLEFT", 24 + (i - 2) * 344, -600)
            end
            control:Show()
        end
    end
    for i, row in ipairs(shop.rows) do
        row.data = menu.rows[i]
        row.requested = false
        row:Hide()
        if row.data then
            row.name:SetText(row.data.link)
            row.price:SetText("#" .. row.data.index .. " | " .. row.data.price .. " vouchers")
            row.price:SetTextColor(1, row.data.price > menu.balance and 0.2 or 0.82, 0)
            row.buy:SetText(row.data.sold and "SOLD" or "Buy")
            if row.data.sold or row.data.price > menu.balance then row.buy:Disable() else row.buy:Enable() end
            itemIcon(row)
            row:Show()
        end
    end
    shop:Show()
end

-- Intercept before the stock frame opens, rather than racing two GOSSIP_SHOW event handlers.
local gossipOnEvent = GossipFrame:GetScript("OnEvent")
GossipFrame:SetScript("OnEvent", function(self, event, ...)
    if event == "GOSSIP_SHOW" then
        local menu = readMenu()
        if menu then showMenu(menu); return end
        dismiss()
    end
    return gossipOnEvent(self, event, ...)
end)

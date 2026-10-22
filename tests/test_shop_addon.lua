-- Offline callback tests. Run from the repository root with lua5.1 or luajit.
-- Widgets model 3.3.5a GossipFrame.xml's closing OnHide and StaticPopup.lua's data/confirm flow.
-- This does not verify native rendering, item-cache requests, or server transactions.
local function equal(actual, expected)
    assert(actual == expected, tostring(actual) .. " ~= " .. tostring(expected))
end
local frames, selections, cache, queries = {}, {}, {}, {}
local options, quests, active = {}, 0, 0
local npc, target = "0xF1300DBD94000001", "0xF1300DBD94000001"
local closes, stockEvents, stockHides, popupShows = 0, 0, 0, 0
local methods = {}
function methods:SetScript(name, callback) self.scripts[name] = callback end
function methods:GetScript(name) return self.scripts[name] end
function methods:RegisterEvent(event) self.events[event] = true end
function methods:SetSize(w, h) self.width, self.height = w, h end
function methods:SetPoint(...) self.point = {...} end
function methods:ClearAllPoints() self.point = nil end
function methods:SetText(value) self.text = value end
function methods:SetTextColor(...) self.color = {...} end
function methods:SetJustifyH(value) equal(value, "LEFT") end
function methods:SetTexture(value) self.texture = value end
function methods:SetFrameStrata(value) equal(value, "DIALOG") end
function methods:EnableMouse(value) self.mouse = value end
function methods:SetMovable(value) self.movable = value end
function methods:RegisterForDrag(value) equal(value, "LeftButton") end
function methods:StartMoving() self.moving = true end
function methods:StopMovingOrSizing() self.moving = false end
function methods:SetBackdrop(value) self.backdrop = value end
function methods:SetBackdropColor(...) self.backdropColor = {...} end
function methods:SetOwner(owner, anchor)
    equal(owner, UIParent); equal(anchor, "ANCHOR_NONE")
    self.owner, self.anchor = owner, anchor
end
function methods:SetHyperlink(link)
    self.link = link
    queries[#queries + 1] = {frame = self, link = link}
end
function methods:Enable() self.enabled = true end
function methods:Disable() self.enabled = false end
function methods:IsShown() return self.shown and (not self.parent or self.parent:IsShown()) end
function methods:Show() self.shown = true end
function methods:Hide()
    local shown = self.shown
    self.shown = false
    if shown and self.scripts.OnHide then self.scripts.OnHide(self) end
end
local function object(parent)
    return setmetatable({scripts = {}, events = {}, shown = true, enabled = true, parent = parent}, {__index = methods})
end
function methods:CreateFontString(_, layer, font)
    equal(layer, "OVERLAY")
    assert(font == "GameFontNormal" or font == "GameFontHighlight" or font == "GameFontNormalLarge")
    return object(self)
end
function methods:CreateTexture(_, layer) equal(layer, "ARTWORK"); return object(self) end
UIParent, UISpecialFrames, StaticPopupDialogs = object(), {}, {}
ACCEPT, CANCEL = "Accept", "Cancel"
function CreateFrame(kind, name, parent, template)
    assert(kind == "Frame" or kind == "Button" or kind == "GameTooltip")
    assert(not template or template == "UIPanelCloseButton" or template == "UIPanelButtonTemplate"
        or template == "GameTooltipTemplate")
    if kind == "GameTooltip" then equal(template, "GameTooltipTemplate") end
    local frame = object(parent)
    if name then assert(not _G[name], name); _G[name] = frame end
    frames[#frames + 1] = frame
    return frame
end
GameTooltip = object()
function GameTooltip:SetOwner(owner, anchor) self.owner = owner; equal(anchor, "ANCHOR_RIGHT") end
function GameTooltip:SetHyperlink(link) self.link = link end
function UnitGUID(unit)
    if unit == "npc" then return npc end
    equal(unit, "target"); return target
end
function GetGossipOptions() return unpack(options) end
function GetNumGossipOptions() return #options / 2 end
function GetNumGossipAvailableQuests() return quests end
function GetNumGossipActiveQuests() return active end
function GetItemInfo(link)
    local entry = tonumber(link:match("|Hitem:([0-9]+):"))
    if cache[entry] then return "Cached item", link, 4, 80, 80, nil, nil, 1, nil, cache[entry] end
end
function CloseGossip() closes = closes + 1 end
function SelectGossipOption(index, code, confirmed)
    selections[#selections + 1] = {index = index, code = code, confirmed = confirmed}
end
function HideUIPanel(frame) frame:Hide() end
local dialog
function StaticPopup_Show(which, arg1, arg2, data)
    StaticPopup_Hide(which)
    popupShows = popupShows + 1
    dialog = {which = which, data = data, shown = true,
        text = string.format(StaticPopupDialogs[which].text, arg1, arg2)}
    return dialog
end
function StaticPopup_Hide(which)
    if dialog and dialog.which == which and dialog.shown then
        dialog.shown = false
        local callback = StaticPopupDialogs[which].OnHide
        if callback then callback(dialog, dialog.data) end
    end
end
local function accept(saved)
    saved = saved or dialog
    StaticPopupDialogs[saved.which].OnAccept(saved, saved.data)
    StaticPopup_Hide(saved.which)
end
local function cancel()
    StaticPopupDialogs[dialog.which].OnCancel(dialog, dialog.data)
    StaticPopup_Hide(dialog.which)
end
GossipFrame = CreateFrame("Frame", "GossipFrameStub", UIParent)
local originalHide = function() stockHides = stockHides + 1; CloseGossip() end
GossipFrame:SetScript("OnHide", originalHide)
-- The real handler shows the stock panel on GOSSIP_SHOW, and hides it on GOSSIP_CLOSED.
local originalEvent = function(self, event)
    stockEvents = stockEvents + 1
    if event == "GOSSIP_SHOW" then self:Show()
    elseif event == "GOSSIP_CLOSED" then HideUIPanel(self) end
end
GossipFrame:SetScript("OnEvent", originalEvent)
GossipFrame:RegisterEvent("GOSSIP_SHOW")
GossipFrame:RegisterEvent("GOSSIP_CLOSED")
local function event(name)
    -- Newly created frames do not get the event already being dispatched.
    local count = #frames
    for i = 1, count do
        local frame = frames[i]
        if frame.events[name] then frame.scripts.OnEvent(frame, name) end
    end
end
local function click(frame, force)
    assert(frame and frame.scripts.OnClick)
    if force or (frame:IsShown() and frame.enabled) then frame.scripts.OnClick(frame, "LeftButton") end
end
local function add(menu, label, kind)
    menu[#menu + 1], menu[#menu + 2] = label, kind or "gossip"
end
local function home(balance)
    local menu = {}
    for _, label in ipairs({"Vouchers: " .. (balance or 3) .. " | Remaining total cost: 80",
        "Weapons / shields / held items", "Armor / cloaks", "Jewelry / trinkets", "Set pieces",
        "Archipelago status / command help"}) do add(menu, label) end
    return menu
end
local function link(entry)
    return "|cffa335ee|Hitem:" .. entry .. ":0:0:0:0:0:0:0:0|h[Server item " .. entry .. "]|h|r"
end
local function page(number, count, nextPage, balance)
    local menu = {}
    add(menu, "Vouchers: " .. (balance or 3) .. " | Remaining total cost: 80")
    add(menu, "Weapons / shields / held items | Page " .. (number or 1) .. " | Back to categories")
    for i = 1, count or 4 do
        local price = ({2, 8, 8, 3})[i] or 1
        add(menu, "#" .. (i - 1) .. " " .. link(1000 + i) .. " | " .. price .. " vouchers | " ..
            (i == 2 and "SOLD" or "Buy one"))
    end
    if number and number > 1 then add(menu, "Previous page") end
    if nextPage then add(menu, "Next page") end
    return menu
end
local function show(menu) options = menu; event("GOSSIP_SHOW") end
local baseline = {}
for key in pairs(_G) do baseline[key] = true end
assert(loadfile("addon/WoWPilago/Shop.lua"))()
equal(WoWPilagoShop, nil) -- No UI or selection until a recognized merchant opens.
show(home())
local shop = WoWPilagoShop
assert(shop:IsShown())
equal(shop.backdrop.bgFile, "Interface\\Buttons\\WHITE8X8")
for i, value in ipairs({0.05, 0.04, 0.03, 1}) do equal(shop.backdropColor[i], value) end
equal(shop.balance.text, "Vouchers: 3    Remaining total cost: 80")
equal(shop.heading.text, "Personal stock categories")
equal(GossipFrame:IsShown(), false)
equal(GossipFrame:GetScript("OnHide"), originalHide)
equal(closes, 0); equal(stockHides, 0); equal(stockEvents, 0); equal(#selections, 0)
equal(UISpecialFrames[1], "WoWPilagoShop")
for i = 1, 5 do
    show(home())
    click(shop.nav[i])
    equal(selections[#selections].index, i + 1)
    equal(selections[#selections].confirmed, nil)
    equal(shop:IsShown(), false)
    click(shop.nav[i], true) -- Waiting for the server cannot send a second selection.
    equal(#selections, i)
end
local before = #selections
local queryCount = #queries
show(page())
equal(#queries - queryCount, 4) -- Cold rows request data without a physical hover.
for i = 1, 4 do
    equal(queries[queryCount + i].frame, WoWPilagoShopQuery)
    equal(queries[queryCount + i].link, link(1000 + i))
end
equal(WoWPilagoShopQuery:IsShown(), false)
shop.scripts.OnUpdate(shop, 0.5)
equal(#queries - queryCount, 4) -- Pending rows do not resend every frame.
equal(shop.heading.text, "Weapons / shields / held items | Page 1")
equal(shop.rows[1].name.text, link(1001))
equal(shop.rows[1].price.text, "#0 | 2 vouchers")
equal(shop.rows[1].buy.text, "Buy"); equal(shop.rows[1].buy.enabled, true)
equal(shop.rows[2].buy.text, "SOLD"); equal(shop.rows[2].buy.enabled, false)
equal(shop.rows[3].buy.text, "Buy"); equal(shop.rows[3].buy.enabled, false)
equal(shop.rows[3].price.color[2], 0.2)
equal(shop.rows[4].buy.enabled, true) -- Exact balance is affordable.
equal(shop.rows[5]:IsShown(), false)
equal(shop.rows[1].icon.texture, "Interface\\Icons\\INV_Misc_QuestionMark")
shop.rows[1].scripts.OnEnter(shop.rows[1])
equal(GameTooltip.link, link(1001)); equal(GameTooltip.owner, shop.rows[1]); assert(GameTooltip:IsShown())
shop.rows[1].scripts.OnLeave(); equal(GameTooltip:IsShown(), false)
cache[1001] = "RealItemIcon"
shop.scripts.OnUpdate(shop, 0.5)
equal(shop.rows[1].icon.texture, "RealItemIcon")
equal(#queries - queryCount, 4)
equal(WoWPilagoShopQuery:IsShown(), false)
equal(#selections, before) -- Show, cache retry and hover never purchase.
click(shop.rows[2].buy, true); click(shop.rows[3].buy, true)
equal(popupShows, 0); equal(#selections, before)
click(shop.rows[1].buy)
equal(dialog.text, "Buy one " .. link(1001) .. " for 2 vouchers?")
equal(#selections, before)
cancel(); equal(dialog.shown, false); equal(shop:IsShown(), true)
click(shop.rows[4].buy)
local confirmed = dialog
accept()
equal(#selections, before + 1)
equal(selections[#selections].index, 6) -- Gossip option 6, NOT stock index 3 or item entry 1004.
equal(selections[#selections].code, ""); equal(selections[#selections].confirmed, true)
equal(shop:IsShown(), false); equal(closes, 0)
accept(confirmed); equal(#selections, before + 1)

-- Cached icons need no query; reopening retries unresolved rows once per fresh menu.
queryCount = #queries
show(page(1, 1)); equal(#queries, queryCount)
show(page()); equal(#queries, queryCount + 3)
shop.scripts.OnUpdate(shop, 0.5); equal(#queries, queryCount + 3)

-- All page directions use the existing option positions, including 12-row pages.
show(page(2, 12, true))
equal(shop.rows[12].price.text, "#11 | 1 vouchers")
click(shop.nav[2]); equal(selections[#selections].index, 15)
show(page(2, 12, true)); click(shop.nav[3]); equal(selections[#selections].index, 16)
show(page()); click(shop.nav[1]); equal(selections[#selections].index, 2)
show(page(1, 12, true)); click(shop.nav[2]); equal(selections[#selections].index, 15)
show(page(1, 0)); equal(shop.rows[1]:IsShown(), false); equal(shop.nav[2]:IsShown(), false)
show(page(1, 4, false, 0)); equal(shop.rows[1].buy.enabled, false)
for _, category in ipairs({"Armor / cloaks", "Jewelry / trinkets", "Set pieces"}) do
    local menu = page()
    menu[3] = category .. " | Page 1 | Back to categories"
    show(menu); equal(shop.heading.text, category .. " | Page 1")
end
local sparse = page()
for i, index in ipairs({7, 23, 85, 119}) do sparse[i * 2 + 3] = sparse[i * 2 + 3]:gsub("^#[0-9]+", "#" .. index) end
show(sparse)
equal(shop.rows[4].price.text, "#119 | 3 vouchers")
click(shop.rows[4].buy); accept()
equal(selections[#selections].index, 6); equal(selections[#selections].confirmed, true)
-- A different city merchant uses a fresh menu, not a cached stock list.
npc, target = "0xF1300DBD94000002", "0xF1300DBD94000002"
event("PLAYER_TARGET_CHANGED")
show(page()); equal(shop.rows[4].price.text, "#3 | 3 vouchers")
npc, target = "0xF1300DBD94000001", "0xF1300DBD94000001"
event("PLAYER_TARGET_CHANGED")

-- Every row remains visible across the supported configured stock sizes.
for _, count in ipairs({30, 60, 120}) do
    local seen = {}
    for number = 1, math.ceil(count / 12) do
        local size = math.min(12, count - (number - 1) * 12)
        local hasNext = number * 12 < count
        local menu = page(number, size, hasNext, 8)
        for i = 1, size do
            local index = (number - 1) * 12 + i - 1
            menu[i * 2 + 3] = "#" .. index .. " " .. link(1000 + index) ..
                " | 1 vouchers | " .. (index % 7 == 0 and "SOLD" or "Buy one")
        end
        show(menu); assert(shop:IsShown())
        for i = 1, size do
            local index = (number - 1) * 12 + i - 1
            assert(not seen[index]); seen[index] = true
            equal(shop.rows[i].name.text, link(1000 + index))
            equal(shop.rows[i].price.text, "#" .. index .. " | 1 vouchers")
            equal(shop.rows[i].buy.enabled, index % 7 ~= 0)
        end
        if hasNext then
            click(shop.nav[number > 1 and 3 or 2])
            equal(selections[#selections].index, size + 3 + (number > 1 and 1 or 0))
        end
    end
    local total = 0
    for index in pairs(seen) do assert(index >= 0 and index < count); total = total + 1 end
    equal(total, count)
end

-- Malformed AP menus fall back to untouched native gossip, never to a partial shop.
local malformed = {{}, {"Unrelated", "vendor"}, home(), home(), page(), page(), page(), page(),
    page(), page(), page(), page(), page(), page(), page(), page(), page(), page(), page(), page()}
malformed[3][1] = "Vouchers: -1 | Remaining total cost: 80"
malformed[4][11] = "Unrelated help"
malformed[5][5] = "#120 " .. link(1001) .. " | 2 vouchers | Buy one"
malformed[6][5] = "#0 |Hitem:1001|h[Fake]|h | 2 vouchers | Buy one"
malformed[7][5] = "#0 " .. link(1001) .. " | 0 vouchers | Buy one"
malformed[8][5] = "#0 " .. link(1001) .. " | 9 vouchers | Buy one"
malformed[9][5] = "#0 " .. link(1001) .. " | 2 vouchers | Unknown"
malformed[10][5] = "#0 " .. link(0) .. " | 2 vouchers | Buy one"
malformed[11][7] = "#0 " .. link(1002) .. " | 2 vouchers | Buy one" -- Duplicate index.
malformed[12][3] = "Unknown category | Page 1 | Back to categories"
malformed[13][3] = "Weapons / shields / held items | Page 11 | Back to categories"
malformed[14][6] = "vendor"
add(malformed[15], "Unexpected extra option")
add(malformed[16], "Next page") -- Cannot be more stock after a partial page.
malformed[17][1] = "Vouchers: 4294967296 | Remaining total cost: 80"
malformed[18][5] = "#0 " .. link(1001) .. " | 2 vouchers | Buy one\n"
malformed[19][5] = {}
malformed[20][1] = "Vouchers: 3 | Remaining total cost: -80"
before = #selections
for _, menu in ipairs(malformed) do
    show(page()); click(shop.rows[1].buy)
    local old = dialog
    local oldCloses, oldEvents = closes, stockEvents
    show(menu)
    equal(shop:IsShown(), false); equal(GossipFrame:IsShown(), true)
    equal(closes, oldCloses); equal(stockEvents, oldEvents + 1); equal(old.shown, false)
    accept(old); equal(#selections, before)
end
for _, change in ipairs({"npc", "target", "quest", "active"}) do
    local oldNpc, oldTarget = npc, target
    if change == "npc" then npc, target = "0xF130000001000001", "0xF130000001000001"
    elseif change == "target" then target = "0xF1300DBD94000002"
    elseif change == "quest" then quests = 1
    else active = 1 end
    local oldEvents = stockEvents
    show(home()); equal(shop:IsShown(), false); equal(stockEvents, oldEvents + 1)
    npc, target, quests, active = oldNpc, oldTarget, 0, 0
end

-- A confirmation is single-use and belongs to exactly one menu snapshot and NPC.
show(page()); click(shop.rows[1].buy)
local stale = dialog
show(page()); accept(stale); equal(#selections, before)
click(shop.rows[1].buy); stale = dialog
options[1] = "Vouchers: 0 | Remaining total cost: 80" -- Changed before GOSSIP_SHOW arrives.
accept(stale); equal(#selections, before); equal(shop:IsShown(), false)
show(page()); click(shop.rows[1].buy); stale = dialog
click(shop.nav[1]); equal(selections[#selections].index, 2)
before = #selections
accept(stale); equal(#selections, before)
show(page()); click(shop.rows[1].buy); stale = dialog
target = "0xF1300DBD94000002"
accept(stale); equal(#selections, before); equal(shop:IsShown(), false)
target = npc
show(page()); click(shop.rows[1].buy); stale = dialog
event("PLAYER_TARGET_CHANGED"); equal(shop:IsShown(), true) -- Same target is safe.
target = nil
local oldCloses = closes
event("PLAYER_TARGET_CHANGED")
equal(shop:IsShown(), false); equal(closes, oldCloses + 1); equal(dialog.shown, false)
accept(stale); equal(#selections, before)
target = npc
show(page()); click(shop.rows[1].buy); stale = dialog
oldCloses = closes
event("GOSSIP_CLOSED")
equal(shop:IsShown(), false); equal(dialog.shown, false); equal(closes, oldCloses)
accept(stale); equal(#selections, before)
show(page()); click(shop.rows[1].buy)
oldCloses = closes
event("PLAYER_LEAVING_WORLD"); equal(shop:IsShown(), false); equal(closes, oldCloses + 1)
show(page()); click(shop.rows[1].buy)
oldCloses = closes
click(WoWPilagoShopClose); equal(shop:IsShown(), false); equal(closes, oldCloses + 1); equal(dialog.shown, false)
show(page())
oldCloses = closes
_G[UISpecialFrames[1]]:Hide() -- Escape's native UISpecialFrames path.
equal(closes, oldCloses + 1); equal(shop:IsShown(), false)
show(page()); options = home()
shop.scripts.OnUpdate(shop, 0.5)
equal(shop:IsShown(), false); equal(#selections, before)

-- Unrelated gossip retains its original close behavior after repeated AP sessions.
show({"Ordinary NPC option", "gossip"})
oldCloses = closes
GossipFrame:Hide(); equal(closes, oldCloses + 1)
assert(stockHides > 0)
equal(GossipFrame:GetScript("OnHide"), originalHide)
for key in pairs(_G) do assert(baseline[key] or key:match("^WoWPilago"), "Unexpected global: " .. key) end
local file = assert(io.open("addon/WoWPilago/WoWPilago.toc"))
local toc = file:read("*a"); file:close()
assert(toc:match("## Interface: 30300\n"))
assert(toc:match("\nCatalog.lua\nWoWPilago.lua\nShop.lua\n"))
print("shop addon tests passed: native fallback, stock/links/cache/tooltips, affordability/SOLD, navigation, explicit confirmation, stale state, closing")

-- Run from the repository root: lua5.1 tests/test_addon.lua
local function equal(actual, expected)
    assert(actual == expected, tostring(actual) .. " ~= " .. tostring(expected))
end

local frames, displayed, items, queries = {}, {}, {}, {}
local immediate, reads = {}, {}
local player, realm = "Tester", "Test Realm"
local loads = 0
UIParent = {}
function UnitName(unit) equal(unit, "player"); return player end
function GetRealmName() return realm end
function GetSpellInfo(spell)
    if spell == 100 then return "Localized Charge", "Rank 1", "ChargeIcon" end
end
assert(loadfile("addon/WoWPilago/Catalog.lua"))()
function GetItemInfo(entry)
    reads[entry] = (reads[entry] or 0) + 1
    if items[entry] then
        return items[entry][1], nil, nil, nil, nil, nil, nil, nil, nil, items[entry][2]
    end
end

local methods = {}
function methods:SetScript(script, callback) self.scripts[script] = callback end
function methods:RegisterEvent(event) self.events[event] = true end
function methods:IsShown() return self.shown end
function methods:Hide()
    self.shown = false
    if self.scripts.OnHide then self.scripts.OnHide(self) end
end
function methods:SetText(text) self.text = text end
function methods:SetTexture(texture) self.texture = texture end
function methods:EnableMouse(enabled) self.mouseEnabled = enabled end
function methods:SetOwner(parent, anchor)
    equal(parent, UIParent)
    equal(anchor, "ANCHOR_NONE")
end
function methods:SetHyperlink(link)
    local entry = tonumber(link:match("^item:([0-9]+):0:0:0:0:0:0:0:0$"))
    assert(entry)
    queries[#queries + 1] = entry
    self.shown = true
    if entry == 4294967295 then error("Unknown item link") end
    if immediate[entry] then items[entry] = immediate[entry] end
end
local function object()
    return setmetatable({scripts = {}, events = {}, shown = false}, {__index = methods})
end

-- Model the named regions and animation timing from original 3.3.5 AlertFrames.xml.
function AchievementFrame_LoadUI() loads = loads + 1 end
function CreateFrame(kind, name, parent, template)
    local frame = object()
    frames[#frames + 1] = frame
    if template == "GameTooltipTemplate" then
        equal(kind, "GameTooltip")
        equal(name, "WoWPilagoReceiptQuery")
        equal(parent, UIParent)
    elseif template then
        equal(loads, 1)
        equal(kind, "Button")
        equal(name, "WoWPilagoToast")
        equal(parent, UIParent)
        equal(template, "AchievementAlertFrameTemplate")
        for _, suffix in ipairs({"Name", "Unlocked", "IconTexture", "Shield"}) do
            _G[name .. suffix] = object()
        end
        WoWPilagoToastShield.shown = true
        frame.scripts.OnClick = function() error("Achievement navigation called") end
        frame.scripts.OnHide = function() error("Real alerts reanchored") end
        _G[name] = frame
    else
        equal(kind, "Frame")
        equal(name, nil)
    end
    return frame
end
function AlertFrame_AnimateIn(frame)
    equal(frame, WoWPilagoToast)
    frame.shown, frame.elapsed = true, 0
    displayed[#displayed + 1] = {
        name = WoWPilagoToastName.text,
        label = WoWPilagoToastUnlocked.text,
        icon = WoWPilagoToastIconTexture.texture,
    }
end

-- Any call to an award/show-achievement API fails rather than silently passing.
function AchievementAlertFrame_ShowAlert() error("Fake achievement") end
function GetAchievementInfo() error("Achievement lookup") end
function AddAchievement() error("Achievement award") end
local realAlert = {sentinel = true}
AchievementAlertFrame1 = realAlert

local originalGlobals = {}
for key in pairs(_G) do originalGlobals[key] = true end
assert(loadfile("addon/WoWPilago/WoWPilago.lua"))()
equal(#frames, 1)
local events = frames[1]
assert(events.events.CHAT_MSG_ADDON)
local function receive(payload, sender, channel, prefix, event)
    events.scripts.OnEvent(events, event or "CHAT_MSG_ADDON", prefix or "WOWPILAGO",
        payload, channel or "WHISPER", sender or "Tester")
end
local function tick(seconds)
    if WoWPilagoToast and WoWPilagoToast.shown then
        WoWPilagoToast.elapsed = WoWPilagoToast.elapsed + seconds
        if WoWPilagoToast.elapsed >= 5.55 then WoWPilagoToast:Hide() end
    end
    if events.scripts.OnUpdate then events.scripts.OnUpdate(events, seconds) end
end

local valid = "ITEM\t0\t118\t2"
for _, channel in ipairs({"PARTY", "RAID", "GUILD", "BATTLEGROUND", "SAY", "whisper"}) do
    receive(valid, "Tester", channel)
end
for _, sender in ipairs({"Other", "Other-TestRealm", "Tester-OtherRealm", "Tester-Test-Realm",
    "Tester-Test'Realm", "Tester-TestRealm-Evil", "Tester-", "tester", "Tester-Test\tRealm"}) do
    receive(valid, sender)
end
receive(valid, "Tester", "WHISPER", "OTHER")
receive(valid, "Tester", "WHISPER", "WOWPILAGO", "OTHER_EVENT")
for _, payload in ipairs({"", "ITEM", "ERROR\t0\t118\t2", "ITEM\t0\t118", "ITEM\t0\t118\t2\textra",
    "ITEM\t-1\t118\t2", "ITEM\t0\t0\t2", "ITEM\t0\t-1\t2", "ITEM\t0\t118\t-1",
    "ITEM\t4294967296\t118\t2", "ITEM\t0\t4294967296\t2", "ITEM\t0\t118\t4294967296",
    "ITEM\t1.5\t118\t2", "ITEM\t1e2\t118\t2", "ITEM\t+1\t118\t2", "ITEM\t 1\t118\t2",
    "ITEM\t0\t118\t2\n", "ITEM\t0\t118\t2\000", "ITEM\t" .. string.rep("9", 256) .. "\t118\t2"}) do
    receive(payload)
end
events.scripts.OnEvent(events, "CHAT_MSG_ADDON", "WOWPILAGO", {}, "WHISPER", "Tester")
events.scripts.OnEvent(events, "CHAT_MSG_ADDON", "WOWPILAGO", valid, "WHISPER", nil)
player = nil
receive(valid, "Tester")
player = "Tester"
realm = nil
receive(valid, "Tester-TestRealm")
realm = "Test Realm"
events.scripts.OnEvent(events, "CHAT_MSG_ADDON", "WOWPILAGO", valid, "WHISPER", {})
tick(0)
equal(#displayed, 0)
equal(#frames, 1)
equal(#queries, 0)

items[118] = {"Minor Healing Potion", "Interface\\Icons\\INV_Potion_49"}
receive(valid)
receive("ITEM\t00\t999\t99") -- Same numeric delivery index, even with different metadata.
tick(0)
equal(#displayed, 1)
equal(displayed[1].name, "Minor Healing Potion")
equal(displayed[1].label, "Archipelago - slot 2")
equal(displayed[1].icon, items[118][2])
equal(WoWPilagoToastShield.shown, false)
equal(WoWPilagoToast.scripts.OnClick, nil)
equal(WoWPilagoToast.mouseEnabled, false)
equal(WoWPilagoToast.scripts.OnHide, nil)
equal(#queries, 0) -- Warm receipts do not create metadata queries.

receive("ITEM\t1\t999\t0", "Tester-TestRealm")
receive("ITEM\t1\t999\t0", "Tester-Test Realm")
receive("ITEM\t2\t120\t3")
tick(1)
equal(#displayed, 1) -- The active toast is not overwritten.
tick(5)
equal(#displayed, 2)
equal(displayed[2].name, "Item #999")
equal(displayed[2].label, "Archipelago - slot 0")
equal(displayed[2].icon, "Interface\\Icons\\INV_Misc_QuestionMark")
equal(#queries, 1)
equal(queries[1], 999)
assert(events.scripts.OnUpdate)
items[999] = {"Localized cold-cache item", "ResolvedIcon"}
tick(0.1)
equal(WoWPilagoToastName.text, "Item #999")
tick(0.4)
equal(WoWPilagoToastName.text, "Localized cold-cache item")
equal(WoWPilagoToastIconTexture.texture, "ResolvedIcon")
equal(#displayed, 2) -- Cache resolution updates the existing toast, not another receipt.
items[120] = {"Newly cached item", "NewIcon"}
tick(6)
equal(#displayed, 3)
equal(displayed[3].name, "Newly cached item")
equal(displayed[3].icon, "NewIcon")
tick(6)
equal(WoWPilagoToast.shown, false)
equal(events.scripts.OnUpdate, nil)
receive(valid)
tick(0)
equal(#displayed, 3) -- Deduplication survives hiding and an empty queue.

receive("ITEM\t4294967295\t4294967295\t4294967295")
tick(0)
equal(#displayed, 4)
equal(displayed[4].name, "Item #4294967295")
equal(displayed[4].label, "Archipelago - slot 4294967295")
equal(loads, 1)
equal(#frames, 3)
equal(queries[#queries], 4294967295) -- Bad link still keeps fallback and normal retirement.
tick(6)
receive("STATE\t3\t919100001\t10\t2")
receive("ITEM\t3\t118\t2")
tick(0)
equal(#displayed, 5)
equal(displayed[5].name, "Progressive Level Cap")
equal(displayed[5].label, "Archipelago - slot 2")
equal(displayed[5].icon, "Interface\\Icons\\Spell_Holy_CrusaderAura")
receive("STATE\t4\t919101100\t100\t1")
receive("SHOP\t0\t118")
receive("SHOP\t0\t118")
tick(6)
equal(displayed[6].name, "Localized Charge")
equal(displayed[6].icon, "ChargeIcon")
tick(6)
equal(displayed[7].name, "Minor Healing Potion")
equal(displayed[7].label, "Equipment purchased")
tick(6)
for _, invalid in ipairs({"STATE\t9\t1\t1\t2", "STATE\t9\t919100001\t-1\t2", "SHOP\t120\t118", "SHOP\t1\t0"}) do
    receive(invalid)
end
tick(0)
equal(#displayed, 7)
receive("STATE\t9\t919100032\t3\t2")
tick(0)
equal(#displayed, 8)
equal(displayed[8].name, "Equipment Voucher +3")
equal(AchievementAlertFrame1, realAlert)
assert(realAlert.sentinel)
tick(6)

-- Cold data resolves while this is the only queued receipt. Partial data keeps its fallback.
receive("ITEM\t10\t1001\t1")
tick(0)
assert(events.scripts.OnUpdate)
local queryCount = #queries
equal(queries[queryCount], 1001)
items[1001] = {"Localized legendary", nil}
tick(0.5)
equal(WoWPilagoToastName.text, "Localized legendary")
equal(WoWPilagoToastIconTexture.texture, "Interface\\Icons\\INV_Misc_QuestionMark")
assert(events.scripts.OnUpdate)
items[1001][2] = "LegendaryIcon"
tick(0.5)
equal(WoWPilagoToastIconTexture.texture, "LegendaryIcon")
equal(events.scripts.OnUpdate, nil)
equal(#queries, queryCount)
receive("ITEM\t010\t118\t9")
tick(0)
equal(#queries, queryCount) -- Visible numeric-identity duplicate neither queries nor animates.
tick(6)

-- A tooltip can populate the cache synchronously, before the first animation.
immediate[1002] = {"Synchronous cache item", "SyncIcon"}
receive("SHOP\t1\t1002")
tick(0)
equal(WoWPilagoToastName.text, "Synchronous cache item")
equal(WoWPilagoToastIconTexture.texture, "SyncIcon")
equal(events.scripts.OnUpdate, nil)
equal(#queries, queryCount + 1)
tick(6)

-- A missing item stops polling after five seconds, without catch-up loops or requery.
receive("ITEM\t11\t1003\t2")
tick(0)
local initialReads, animations = reads[1003], #displayed
queryCount = #queries
tick(4)
equal(reads[1003], initialReads + 1)
equal(#queries, queryCount)
tick(1)
equal(events.scripts.OnUpdate, nil)
assert(WoWPilagoToast.shown)
items[1003] = {"Too late", "LateIcon"}
receive("ITEM\t11\t1003\t2")
tick(0.1)
equal(WoWPilagoToastName.text, "Item #1003")
equal(#displayed, animations)
equal(#queries, queryCount)
tick(0.5)

-- Hiding an unresolved toast retires it. Late data cannot overwrite the following state toast.
receive("ITEM\t12\t1004\t2")
tick(0)
receive("STATE\t13\t919100032\t3\t2")
WoWPilagoToast:Hide()
tick(0)
equal(WoWPilagoToastName.text, "Equipment Voucher +3")
items[1004] = {"Old hidden item", "OldIcon"}
tick(0.5)
equal(WoWPilagoToastName.text, "Equipment Voucher +3")
equal(events.scripts.OnUpdate, nil)
tick(6)
for _, frame in ipairs(frames) do
    assert(not frame.shown, "Metadata tooltip or toast leaked visible state")
end

for key in pairs(_G) do
    assert(originalGlobals[key] or key:match("^WoWPilago"), "Unexpected global: " .. key)
end
for _, frame in ipairs(frames) do
    for event in pairs(frame.events) do
        assert(frame == events and event == "CHAT_MSG_ADDON")
    end
end
local file = assert(io.open("addon/WoWPilago/WoWPilago.toc"))
local toc = file:read("*a")
file:close()
assert(toc:match("## Interface: 30300\n"))
assert(toc:match("\nWoWPilago.lua\n"))
print("addon tests passed: item/state/shop feedback, filters, bounds, stock-template text/icon, FIFO, fallback, deduplication")

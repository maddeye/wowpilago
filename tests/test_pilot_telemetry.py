import math
from pathlib import Path
import subprocess
import unittest
from pilot_telemetry import SCHEMA, checksum, decode, Freshness
from integration_inputs import require_inputs

ADDON = Path(__file__).resolve().parents[1] / '.local/v2-client/game/Interface/AddOns/WoWPilagoPilot/WoWPilagoPilot.lua'


def packet(seq=1, **changes):
    values = dict(magic=b'WP', version=1, seq=seq, flags=3, valid=127, area=9,
                  x=0, y=65535, facing=0, hp=100, thp=0, money=4294967295, quest=2, tail=seq)
    values.update(changes)
    data = SCHEMA.pack(*values.values())
    return data + checksum(data)


def image(data, black=25, white=230):
    return bytes(white if data[((y//4)*16+x//4)//8] & (1 << (((y//4)*16+x//4)%8)) else black
                 for y in range(64) for x in range(64) for channel in range(3))


class TelemetryTests(unittest.TestCase):
    def test_roundtrip_and_roi(self):
        result = decode(image(packet()))
        self.assertEqual((result['map_x'], result['map_y'], result['facing']), (0, 1, 0))
        self.assertEqual((result['money'], result['target_health'], result['quest7_count']), (4294967295, 0, 2))
        self.assertTrue(result['target_dead'])
        self.assertIsNone(decode(image(packet(valid=0)))['player_health'])
        self.assertAlmostEqual(decode(image(packet(facing=65535)))['facing'], math.tau, delta=.0001)
        roi = bytes(70*70*3)
        roi = bytearray(roi)
        for row in range(64):
            roi[((row+3)*70+2)*3:((row+3)*70+66)*3] = image(packet())[row*192:(row+1)*192]
        self.assertEqual(decode(roi, 70, 70, 2, 3), result)

    def test_rejections(self):
        torn = packet()[:16] + packet(seq=2, hp=50)[16:]
        for raw in (b'', bytes(12288), image(packet(magic=b'NO')), image(packet(version=2)),
                    image(packet(quest=9)), image(packet(x=0, y=0)), image(packet(flags=0)),
                    image(packet(tail=2)), image(torn), image(packet(), 120, 130)):
            with self.assertRaises(ValueError): decode(raw)
        self.assertEqual(decode(image(packet(), 80, 175))['sequence'], 1)
        raw = bytearray(image(packet())); raw[390:393] = b'\xff\x00\xff'
        with self.assertRaises(ValueError): decode(raw)

    def test_freshness(self):
        gate = Freshness()
        for seq, now, accepted in ((65535, 0, False), (0, .1, True), (0, .2, False),
                                   (65535, .3, False), (1, .7, False), (2, .8, True)):
            if accepted: self.assertEqual(gate.observe(image(packet(seq)), now)['sequence'], seq)
            else:
                with self.assertRaises(ValueError): gate.observe(image(packet(seq)), now)
        with self.assertRaises(ValueError): gate.observe(b'', .9)
        with self.assertRaises(ValueError): gate.observe(image(packet(3)), 1)

    def test_actual_lua(self):
        require_inputs(ADDON)
        harness = r'''
local pixels, scripts = {}, {}
local methods = setmetatable({}, {__index=function() return function() end end})
function methods:GetEffectiveScale() return .75 end
function methods:SetScript(k,v) scripts[k]=v end
function methods:CreateTexture() local t=setmetatable({}, {__index=methods}); pixels[#pixels+1]=t; return t end
function methods:SetTexture(v) self.bit=v end
UIParent=setmetatable({}, {__index=methods})
function CreateFrame() return setmetatable({}, {__index=methods}) end
local x,y,angle,hp = 0,1,0,100
function GetPlayerMapPosition() return x,y end
function GetCurrentMapAreaID() return 9 end
function GetPlayerFacing() return angle end
function UnitExists() return true end
function UnitIsDead(unit) return unit=='target' end
function UnitCanAttack() return true end
function UnitAffectingCombat() return false end
function UnitHealth(unit) if unit=='player' then return hp else return 0 end end
function GetMoney() return 4294967295 end
function GetNumQuestLogEntries() return 1 end
function GetQuestLink() return '|Hquest:7:1|h' end
function GetQuestLogLeaderBoard() return 'Kobolds slain: 2/8' end
local resets=0; function SetMapToCurrentZone() resets=resets+1 end
'''
        checks = r'''
local function dump()
 scripts.OnUpdate(nil,.1)
 for i=0,31 do local b=0; for j=0,7 do b=b+pixels[i*8+j+1].bit*2^j end; io.write(string.char(b)) end
end
scripts.OnUpdate(nil,.05); assert(pixels[1].bit==0)
scripts.OnEvent(nil,'PLAYER_ENTERING_WORLD'); assert(resets==1)
dump(); angle=2*math.pi; x,y=1,0; dump()
hp=-1; GetMoney=function() return nil end; GetPlayerFacing=nil; dump()
x,y=0,0; dump(); assert(resets==1)
hp=4294967296; UnitExists=function() return false end; dump()
UnitIsDead=nil; dump()
'''
        result = subprocess.run(['luajit', '-e', harness + '\ndofile(' + repr(str(ADDON)) + ')\n' + checks], check=True, capture_output=True)
        frames = [decode(image(result.stdout[i:i+32])) for i in range(0, len(result.stdout), 32)]
        self.assertEqual(len(frames), 6)
        self.assertEqual((frames[0]['facing'], frames[1]['facing']), (0, 0))
        self.assertEqual((frames[1]['map_x'], frames[1]['map_y']), (1, 0))
        self.assertTrue(all(frames[2][key] is None for key in ('player_health', 'money', 'facing')))
        self.assertIsNone(frames[3]['map_area'])
        self.assertIsNone(frames[4]['player_health'])
        self.assertIsNone(frames[4]['target_health'])
        self.assertFalse(frames[4]['target_exists'])
        self.assertIsNone(frames[5]['target_dead'])


if __name__ == '__main__': unittest.main()

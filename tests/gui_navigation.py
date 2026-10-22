"""Small normal-input lever for the private :94 client. No movement API calls."""
import argparse
import math
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / '.local/v2-client/game/Logs/WoWChatLog.txt'
WINDOW = '8388611'


def turn_delta(current, desired):
    return (desired - current + math.pi) % (2 * math.pi) - math.pi


def parse_probe(text, marker):
    matches = re.findall(re.escape(marker) + r' ([0-9.]+) ([0-9.]+) ([0-9.]+)', text)
    if not matches:
        raise ValueError('No fresh client probe in chat log')
    return tuple(map(float, matches[-1]))


def xdo(*args):
    subprocess.run(['xdotool', *map(str, args)], env={**os.environ, 'DISPLAY': ':94'}, check=True)


def chat(text):
    if len(text) > 255 or '\n' in text:
        raise ValueError('One normal chat line, at most 255 characters')
    xdo('windowfocus', '--sync', WINDOW)
    xdo('key', 'Return')
    time.sleep(.2)
    xdo('type', '--clearmodifiers', '--delay', '8', text)
    time.sleep(.2)
    xdo('key', 'Return')
    time.sleep(.4)


def hold(key, seconds):
    if key not in ('w', 's', 'a', 'd') or not 0 < seconds <= 5:
        raise ValueError('Only bounded normal movement keys')
    xdo('windowfocus', '--sync', WINDOW)
    try:
        xdo('keydown', key)
        time.sleep(seconds)
    finally:
        xdo('keyup', key)


def probe():
    marker = 'NAV' + str(time.time_ns())
    chat('/run LoggingChat(true)')
    chat('/run local x,y=GetPlayerMapPosition("player"); SendChatMessage(format("' + marker + ' %.5f %.6f %.6f",GetPlayerFacing(),x,y),"WHISPER",nil,UnitName("player"))')
    chat('/run LoggingChat(false)')
    time.sleep(.3)
    try:
        result = parse_probe(LOG.read_text(errors='replace'), marker)
    except (FileNotFoundError, ValueError):
        print('Chat log buffered. Read fresh probe in client screenshot; no automatic turn.', flush=True)
        return None
    print(result, flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['probe', 'turn', 'hold', 'chat', 'shot'])
    parser.add_argument('values', nargs='*')
    args = parser.parse_args()
    if args.action == 'probe':
        probe()
    elif args.action == 'turn':
        # shortcut: stock turn rate is approximate; observe the probe before walking.
        delta = turn_delta(*map(float, args.values))
        if abs(delta) > .01:
            hold('a' if delta > 0 else 'd', abs(delta) / math.pi)
        probe()
    elif args.action == 'hold':
        hold(args.values[0], float(args.values[1]))
    elif args.action == 'chat':
        chat(args.values[0])
    else:
        destination = ROOT / '.local/v2-navigation' / (Path(args.values[0]).name + '.png')
        subprocess.run(['import', '-window', WINDOW, str(destination)], env={**os.environ, 'DISPLAY': ':94'}, check=True)


if __name__ == '__main__':
    main()

"""Real two-game generation and private server. Protocol fixtures are NOT gameplay."""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import tempfile
import zipfile
import zlib

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = Path('/tmp/archipelago-upstream')
PIN = '54803be064fc7e80c4628777ed0b46a9390f255f'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    paths = sorted((PROJECT / 'apworld/wowpilago').rglob('*'))
    paths += [PROJECT / 'examples/player.yaml', PROJECT / 'examples/checksfinder.yaml']
    return {str(p.relative_to(PROJECT)): digest(p) for p in paths
            if p.is_file() and p.suffix in {'.py', '.json', '.yaml'}}


def setup(upstream, root):
    commit = subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != PIN:
        raise RuntimeError(f'Expected AP {PIN}, found {commit}')
    os.environ['AP_TEST_WORLDS'] = 'wowpilago,checksfinder'
    os.environ['SKIP_REQUIREMENTS_UPDATE'] = '1'
    sys.path.insert(0, str(upstream))
    os.chdir(root)
    import Utils
    Utils.user_path.cached_path = str(root)
    return commit


def current(root):
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest['source_sha256'] != source_hashes():
        raise RuntimeError('Source/catalog changed. Generate a NEW room; do not reuse this seed/save.')
    for name, expected in manifest['artifact_sha256'].items():
        if digest(root / name) != expected:
            raise RuntimeError(f'Artifact changed: {name}')
    return manifest


def generate(args):
    base = PROJECT / '.local/v2-multiworld'
    base.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix='run-', dir=base)).resolve()
    before = source_hashes()
    commit = setup(args.upstream, root)
    worlds = root / 'worlds'
    worlds.mkdir()
    with zipfile.ZipFile(worlds / 'wowpilago.apworld', 'w') as archive:
        for name in before:
            if name.startswith('apworld/'):
                archive.write(PROJECT / name, name.removeprefix('apworld/'))
    players = root / 'players'
    players.mkdir()
    for name in ('player.yaml', 'checksfinder.yaml'):
        (players / name).write_bytes((PROJECT / 'examples' / name).read_bytes())
    import Generate
    import Main
    import Utils
    options = Generate.mystery_argparse([
        '--player_files_path', str(players), '--outputpath', str(root / 'output'),
        '--seed', str(args.seed), '--spoiler', '1',
    ])
    Main.main(*Generate.main(options))
    generated, = (root / 'output').glob('AP_*.zip')
    with zipfile.ZipFile(generated) as archive:
        name, = [n for n in archive.namelist() if n.endswith('.archipelago')]
        raw = archive.read(name)
        multidata_path = root / Path(name).name
        multidata_path.write_bytes(raw)
    data = Utils.restricted_loads(zlib.decompress(raw[1:]))
    slots = {info.game: slot for slot, info in data['slot_info'].items()}
    assert set(slots) == {'World of Warcraft', 'ChecksFinder'}, slots
    wow, checks = slots['World of Warcraft'], slots['ChecksFinder']
    slot = data['slot_data'][wow]
    assert slot['protocol_version'] == 2
    assert slot['profile']['race_id'] == 1 and slot['profile']['class_id'] == 1
    assert set(data['locations'][wow]) == {c['ap_id'] for c in slot['selected_checks']}
    assert len(data['locations'][checks]) == 25
    from worlds.AutoWorld import AutoWorldRegister
    placements = []
    for sender, locations in data['locations'].items():
        sender_game = data['slot_info'][sender].game
        location_names = AutoWorldRegister.world_types[sender_game].location_id_to_name
        for location, (item, recipient, flags) in locations.items():
            recipient_game = data['slot_info'][recipient].game
            item_names = AutoWorldRegister.world_types[recipient_game].item_id_to_name
            placements.append(dict(sender=sender, sender_game=sender_game, location=location,
                                   location_name=location_names[location], item=item,
                                   item_name=item_names[item], recipient=recipient,
                                   recipient_game=recipient_game, flags=flags))
    for sender, recipient in ((wow, checks), (checks, wow)):
        assert any(p['sender'] == sender and p['recipient'] == recipient for p in placements)
    (root / 'slot-data.json').write_text(json.dumps(data['slot_data'], indent=2) + '\n')
    (root / 'placements.json').write_text(json.dumps(placements, indent=2) + '\n')
    if before != source_hashes():
        raise RuntimeError(f'Source changed during generation; discard {root} and retry')
    artifacts = [worlds / 'wowpilago.apworld', generated, multidata_path,
                 root / 'slot-data.json', root / 'placements.json', *players.iterdir()]
    manifest = dict(upstream=commit, python=sys.executable, python_version=sys.version,
                    generator_sha256=digest(Path(__file__)), seed=args.seed,
                    catalog_version=slot['catalog_version'], source_sha256=before,
                    multidata=multidata_path.name,
                    artifact_sha256={str(p.relative_to(root)): digest(p) for p in artifacts},
                    scope='Real packaged generation only; native WoW delivery NOT verified.')
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'PASS real two-game fill and extracted slot data/placements: {root}')
    print(shlex.join([sys.executable, str(Path(__file__).resolve()), 'server', str(root),
                      '--upstream', str(args.upstream), '--port', '38283']))


def server(args):
    root = args.run.resolve()
    manifest = current(root)
    setup(args.upstream, root)
    if args.port == 38282:
        raise ValueError('38282 is reserved for the old room')
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    command = [sys.executable, str(args.upstream / 'MultiServer.py'),
               str(root / manifest['multidata']), '--host', '127.0.0.1',
               '--port', str(args.port), '--disable_item_cheat', '--release_mode', 'disabled', '--collect_mode', 'disabled']
    # Keep the isolated user path when executing the real server entry point.
    sys.argv = command[1:]
    import runpy
    runpy.run_path(command[1], run_name='__main__')


async def protocol_fixture(args):
    """Send generated checks over real AP transport, never call this real play."""
    root = args.run.resolve()
    current(root)
    setup(args.upstream, root)
    from NetUtils import encode, decode, NetworkItem
    from Utils import version_tuple
    import websockets
    placements = json.loads((root / 'placements.json').read_text())
    slots = json.loads((root / 'slot-data.json').read_text())
    wow = next(int(s) for s, d in slots.items() if d.get('protocol_version') == 2)
    checks = next(int(s) for s in slots if int(s) != wow)
    connections = {}
    evidence = []

    async def until(ws, predicate):
        async with asyncio.timeout(15):
            while True:
                for packet in decode(await ws.recv()):
                    if packet['cmd'] == 'ConnectionRefused':
                        raise RuntimeError(packet)
                    if predicate(packet):
                        return packet

    try:
        for slot, game, name in ((wow, 'World of Warcraft', 'Azeroth'),
                                 (checks, 'ChecksFinder', 'ChecksFinder')):
            ws = await websockets.connect(f'ws://127.0.0.1:{args.port}')
            connections[slot] = ws
            await until(ws, lambda p: p['cmd'] == 'RoomInfo')
            await ws.send(encode([dict(cmd='Connect', password=None, game=game, name=name,
                                      uuid=f'protocol-fixture-{slot}', version=version_tuple,
                                      items_handling=7, tags=['AP'], slot_data=True)]))
            connected = await until(ws, lambda p: p['cmd'] == 'Connected')
            assert connected['slot'] == slot
            assert connected['slot_data'] == slots[str(slot)], 'Wrong room/seed/slot data'
            assert not connected['checked_locations'], 'Use a fresh fixture-only room/save'
        for sender, recipient in ((wow, checks), (checks, wow)):
            placement = next(p for p in placements if p['sender'] == sender and p['recipient'] == recipient)
            await connections[sender].send(encode([dict(cmd='LocationChecks', locations=[placement['location']])]))
            def received(packet):
                return packet['cmd'] == 'ReceivedItems' and any(
                    NetworkItem(*item).item == placement['item'] and
                    NetworkItem(*item).location == placement['location'] and
                    NetworkItem(*item).player == sender for item in packet['items'])
            packet = await until(connections[recipient], received)
            evidence.append(dict(placement=placement, received=packet))
        (root / 'protocol-fixture.json').write_text(json.dumps(dict(
            scope='Fabricated checks, real MultiServer routing only. NOT game play or native delivery.',
            evidence=evidence), indent=2) + '\n')
        print('PASS bidirectional real server routing ONLY; checks are protocol fixtures, not gameplay')
    finally:
        for ws in connections.values():
            await ws.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('generate', 'server', 'protocol-fixture', 'check-current'):
        sub = commands.add_parser(command)
        sub.add_argument('--upstream', type=Path, default=DEFAULT_UPSTREAM)
        if command == 'generate':
            sub.add_argument('--seed', type=int, default=919000203)
        else:
            sub.add_argument('run', type=Path)
        if command in ('server', 'protocol-fixture'):
            sub.add_argument('--port', type=int, default=38283)
    args = parser.parse_args()
    args.upstream = args.upstream.resolve()
    if args.command == 'generate':
        generate(args)
    elif args.command == 'server':
        server(args)
    elif args.command == 'protocol-fixture':
        if args.port == 38282:
            parser.error('38282 is reserved for the old room')
        asyncio.run(protocol_fixture(args))
    else:
        current(args.run.resolve())
        print('PASS source and artifact checksums still match')


if __name__ == '__main__':
    main()

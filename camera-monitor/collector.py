"""Root eBPF supervisor: event journal, uevents and sparse handle reconciliation."""
import argparse
from collections import deque
import datetime
import importlib.util
import json
import os
from pathlib import Path
import selectors
import socket
import subprocess
import sys
sys.dont_write_bytecode = True
import time
import uuid

spec = importlib.util.spec_from_file_location('camera_scan', Path(__file__).with_name('monitor.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def event_record(raw, devices, seq):
    key = (raw['major'], raw['minor'])
    name = devices.get(key, f'char{key[0]}:{key[1]}')
    comm = m.clean(raw['name'])
    start = str(raw['start_ns'] // (1_000_000_000 // os.sysconf('SC_CLK_TCK')))
    executable = 'unavailable (process exited or changed identity)'
    try:
        proc = Path('/proc') / str(raw['pid'])
        stat = (proc / 'stat').read_text()
        if stat[stat.rfind(')') + 2:].split()[19] == start:
            executable = m.clean(os.readlink(proc / 'exe'))
    except (OSError, IndexError):
        pass
    epoch = time.time() - time.clock_gettime(time.CLOCK_BOOTTIME) + raw['time_ns'] / 1e9
    virtual = Path('/sys/class/video4linux') / name
    infrastructure = comm.startswith('v4l2-relay') and '/devices/virtual/' in str(virtual.resolve())
    return {'seq': seq, 'time': datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat(),
            'action': 'opened' if raw['action'] == 1 else 'released',
            'uid': raw['uid'], 'pid': raw['pid'], 'start': start, 'name': comm,
            'executable': executable, 'devices': [name], 'broker': comm.startswith(('pipewire', 'v4l2-relay')),
            'infrastructure': infrastructure, 'known': bool(raw['known']), 'source': 'ebpf'}


def snapshot_trace(snapshot, stream, records, lost, ready=True, error=None):
    value = {**snapshot, 'time': time.time(), 'events': list(records),
             'trace': {'backend': 'ebpf', 'ready': ready, 'lost': lost, 'stream': stream, 'error': error}}
    if not ready:
        value['state'] = 'unavailable'
    elif lost and value['state'] != 'access':
        value['state'] = 'partial'
    return value


def run(engine, obj, output):
    devices = m.discover()
    stream = uuid.uuid4().hex
    records = deque(maxlen=200)
    snapshot = {'devices': sorted(devices.values()), 'holders': [], 'unreadable': [], 'coverage': 'system', 'state': 'unavailable'}
    process = None
    netlink = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM | socket.SOCK_NONBLOCK, 15)
    netlink.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1 << 20)
    netlink.bind((os.getpid(), 1))
    poller = selectors.DefaultSelector()
    poller.register(netlink, selectors.EVENT_READ, 'hotplug')
    lost = 0
    native_lost = 0
    hotplug_lost = 0
    ready = False
    try:
        m.save(output, snapshot_trace(snapshot, stream, records, lost, False, 'Attaching kernel hooks…'), 0o640)
        process = subprocess.Popen([engine, obj, *[f'{a}:{b}' for a, b in devices]],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        os.set_blocking(process.stdout.fileno(), False)
        poller.register(process.stdout, selectors.EVENT_READ, 'engine')
        buffer = b''
        scan_due = float('inf')
        last_scan = 0.0
        publish_due = 0.0
        last_heartbeat = time.monotonic()
        seq = 0
        while True:
            now = time.monotonic()
            if process.poll() is not None:
                raise RuntimeError(f'eBPF engine exited ({process.returncode})')
            deadline = min(scan_due, publish_due, last_scan + 60 if ready else float('inf'))
            for key, _ in poller.select(timeout=max(0, min(1, deadline - now))):
                if key.data == 'hotplug':
                    try:
                        data, address = netlink.recvfrom(65536)
                    except BlockingIOError:
                        continue
                    except OSError as exc:
                        # Netlink queue overrun: resynchronize device inventory;
                        # history completeness cannot be restored by a scan.
                        if exc.errno != 105:
                            raise
                        hotplug_lost += 1
                        lost = native_lost + hotplug_lost
                        data, address = b'SUBSYSTEM=video4linux\0', (0, 0)
                    if address[0] != 0:
                        continue
                    if not any(x in data.split(b'\0') for x in (b'SUBSYSTEM=video4linux', b'SUBSYSTEM=media')):
                        continue
                    new = m.discover()
                    for pair in new.keys() - devices.keys():
                        process.stdin.write(f'+ {pair[0]}:{pair[1]}\n'.encode())
                    for pair in devices.keys() - new.keys():
                        process.stdin.write(f'- {pair[0]}:{pair[1]}\n'.encode())
                    process.stdin.flush()
                    devices = new
                    scan_due = min(scan_due, now + 0.05)
                else:
                    chunk = os.read(process.stdout.fileno(), 65536)
                    if not chunk:
                        raise RuntimeError('eBPF engine output closed')
                    buffer += chunk
                    if len(buffer) > 1 << 20:
                        raise RuntimeError('Invalid oversized eBPF output')
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        raw = json.loads(line)
                        if raw['kind'] == 'ready':
                            ready = True
                            scan_due = now
                        elif raw['kind'] == 'heartbeat':
                            last_heartbeat = now
                            # Native losses never decrease during an engine run.
                            native_lost = max(native_lost, raw['lost'])
                            lost = native_lost + hotplug_lost
                        elif raw['kind'] == 'event':
                            seq += 1
                            if (raw['major'], raw['minor']) not in devices:
                                devices.update(m.discover())
                            records.append(event_record(raw, devices, seq))
                            scan_due = min(scan_due, now + 0.05)
                            publish_due = min(publish_due, now + 0.05)
                        else:
                            raise RuntimeError('Unexpected eBPF message')
            now = time.monotonic()
            if now - last_heartbeat > 5:
                raise RuntimeError('eBPF engine heartbeat lost')
            # Events drive scans, with bounded burst coalescing. The 60-second
            # reconciliation covers inherited/passed handles and inventory races.
            if ready and (now >= scan_due or now - last_scan >= 60):
                snapshot = m.scan(devices=devices, uid=-1)
                last_scan = now
                scan_due = float('inf')
                publish_due = min(publish_due, now)
            if now >= publish_due:
                m.save(output, snapshot_trace(snapshot, stream, records, lost, ready), 0o640)
                publish_due = now + 1
    except BaseException as exc:
        m.save(output, snapshot_trace(snapshot, stream, records, lost, False, str(exc)[:240]), 0o640)
        raise
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        poller.close()
        netlink.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--object', required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Root is required for the system collector')
    run(args.engine, args.object, Path('/run/camera-monitor/status.json'))

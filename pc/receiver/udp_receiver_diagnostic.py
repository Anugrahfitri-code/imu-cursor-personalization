"""Bench-only receiver instrumentation, v1. Original receiver stays unchanged."""
import argparse
import csv
import hashlib
import json
import platform
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_SHA256 = '7013513accc8140b9286203fec41c6f29d2aa47b69ef2d44f50eceda4dd556a9'
RAW_FIELDS = ['pc_receive_monotonic_ns', 'pc_receive_wall_ns', 'source_ip',
              'source_port', 'protocol_version', 'session_id', 'record_name',
              'seq_global', 'seq_sensor', 'sensor_type', 'sensor_ts_phone_ns',
              'callback_elapsed_ns', 'send_elapsed_ns', 'x', 'y', 'z', 'accuracy']
TIME_FIELDS = ['event_index', 'status', 'session_id', 'seq_global',
               'thread_cpu_before_ns', 'recv_before_ns', 'recv_after_ns',
               'wall_after_ns', 'parse_before_ns', 'parse_after_ns',
               'stats_before_ns', 'stats_after_ns', 'write_before_ns',
               'write_after_ns', 'flush_before_ns', 'flush_after_ns',
               'print_before_ns', 'print_after_ns', 'thread_cpu_after_ns',
               'cycle_end_ns', 'error']


def load_base():
    path = Path(__file__).with_name('udp_receiver.py')
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != BASE_SHA256:
        raise RuntimeError('Original udp_receiver.py missing or SHA256 differs. No capture started.')
    import udp_receiver
    return udp_receiver


def run(args, base):
    # Default socket size, timeout, synchronous CSV and 200-packet flush/print
    # intentionally match the original. This is instrumentation, not a fix.
    root = Path(args.output_root)
    out = root / ('diag_' + datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir(parents=True, exist_ok=False)
    events, sessions = [], {}
    valid = invalid = 0
    reason = 'initializing'
    metadata = {'diagnostic_version': 1, 'base_sha256': BASE_SHA256,
                'diagnostic_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                'python': sys.version, 'platform': platform.platform(),
                'args': vars(args), 'monotonic': vars(time.get_clock_info('monotonic')),
                'wall_clock': vars(time.get_clock_info('time')),
                'timing_units': 'ns', 'missing_scope': 'received sequence range only',
                'warning': 'Instrumentation adds overhead; duration is not proof of cause.'}
    (out / 'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    print(f'Output directory: {out.resolve()}', flush=True)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind((args.host, args.port))
            sock.settimeout(base.SOCKET_TIMEOUT_SECONDS)
            metadata['socket_rcvbuf_bytes'] = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
            print(f'Listening on {args.host}:{args.port}. Stop Android first, then Ctrl+C.', flush=True)
            with (out / 'raw.csv').open('x', newline='', encoding='utf-8') as raw:
                writer = csv.writer(raw)
                writer.writerow(RAW_FIELDS)
                raw.flush()
                reason = 'running'
                while True:
                    if len(events) >= args.max_events:
                        reason = 'diagnostic_event_limit'
                        break
                    e = dict.fromkeys(TIME_FIELDS, '')
                    e.update(event_index=len(events) + 1, status='partial')
                    try:
                        e['thread_cpu_before_ns'] = time.thread_time_ns()
                        e['recv_before_ns'] = time.monotonic_ns()
                        try:
                            data, addr = sock.recvfrom(base.BUFFER_SIZE)
                        except socket.timeout:
                            e['recv_after_ns'] = time.monotonic_ns()
                            e['status'] = 'timeout'
                            continue
                        e['recv_after_ns'] = time.monotonic_ns()
                        e['wall_after_ns'] = time.time_ns()
                        e['parse_before_ns'] = time.monotonic_ns()
                        try:
                            packet = base.parse_data_packet(data.decode('utf-8'))
                        except Exception as exc:
                            e['parse_after_ns'] = time.monotonic_ns()
                            e.update(status='invalid', error=str(exc))
                            invalid += 1
                            e['print_before_ns'] = time.monotonic_ns()
                            print('[INVALID]', exc)
                            e['print_after_ns'] = time.monotonic_ns()
                            continue
                        e['parse_after_ns'] = time.monotonic_ns()
                        e.update(session_id=packet.session_id, seq_global=packet.seq_global)
                        e['stats_before_ns'] = time.monotonic_ns()
                        valid += 1
                        if packet.session_id not in sessions:
                            sessions[packet.session_id] = base.SessionStats()
                        stats = sessions[packet.session_id]
                        base.update_session_stats(stats, packet.seq_global)
                        e['stats_after_ns'] = time.monotonic_ns()
                        e['write_before_ns'] = time.monotonic_ns()
                        writer.writerow([e['recv_after_ns'], e['wall_after_ns'], *addr,
                            packet.protocol_version, packet.session_id, packet.record_name,
                            packet.seq_global, packet.seq_sensor, packet.sensor_type,
                            packet.sensor_ts_phone_ns, packet.callback_elapsed_ns,
                            packet.send_elapsed_ns, packet.x, packet.y, packet.z, packet.accuracy])
                        e['write_after_ns'] = time.monotonic_ns()
                        if valid % 200 == 0:
                            e['flush_before_ns'] = time.monotonic_ns()
                            raw.flush()
                            e['flush_after_ns'] = time.monotonic_ns()
                            e['print_before_ns'] = time.monotonic_ns()
                            expected = stats.last_seq - stats.first_seq + 1
                            loss = 100 * stats.missing_packets / expected
                            print(f'session={packet.record_name} packets={stats.packet_count} '
                                  f'last_seq={stats.last_seq} missing={stats.missing_packets} '
                                  f'loss={loss:.4f}% duplicate={stats.duplicate_packets} '
                                  f'out_of_order={stats.out_of_order}')
                            e['print_after_ns'] = time.monotonic_ns()
                        e['status'] = 'valid'
                    finally:
                        e['thread_cpu_after_ns'] = time.thread_time_ns()
                        e['cycle_end_ns'] = time.monotonic_ns()
                        events.append(e)
                    if args.max_valid_packets and valid >= args.max_valid_packets:
                        reason = 'max_valid_packets_test_only'
                        break
    except KeyboardInterrupt:
        reason = 'keyboard_interrupt'
    except Exception as exc:
        reason = 'error'
        metadata['error'] = repr(exc)
        raise
    finally:
        # Timing CSV is written only after socket closes, not in acquisition loop.
        with (out / 'timing.csv').open('x', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=TIME_FIELDS)
            writer.writeheader()
            writer.writerows(events)
        summary = {'stop_reason': reason, 'valid_packets': valid,
                   'invalid_packets': invalid, 'timing_events': len(events), 'sessions': {}}
        for sid, s in sessions.items():
            summary['sessions'][sid] = {'received': s.packet_count,
                'unique_received': len(s.received_sequences), 'first_seq': s.first_seq,
                'last_seq': s.last_seq, 'missing_within_received_range': s.missing_packets,
                'duplicate': s.duplicate_packets, 'out_of_order': s.out_of_order,
                'longest_missing_burst_within_range': s.longest_missing_burst}
        metadata['summary'] = summary
        (out / 'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print(json.dumps(summary, indent=2))
        print(f'Saved to: {out.resolve()}')
    return 2 if reason == 'diagnostic_event_limit' else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate original hash/import, without binding socket.')
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=5005)
    parser.add_argument('--output-root', default=str(Path(__file__).resolve().parent / 'logs_diagnostic'))
    parser.add_argument('--max-events', type=int, default=100000,
                        help='Memory guard, includes timeout/invalid events. Intended for short bench only.')
    parser.add_argument('--max-valid-packets', type=int, default=0, help='TEST ONLY: auto-stop after N valid packets.')
    args = parser.parse_args()
    if args.max_events < 1 or args.max_valid_packets < 0 or not 1 <= args.port <= 65535:
        parser.error('Invalid event limit, packet limit or port.')
    base = load_base()
    if args.check:
        print('CHECK OK: original SHA256 matches; parser/stats import succeeded; no socket opened.')
        return 0
    return run(args, base)


if __name__ == '__main__':
    raise SystemExit(main())

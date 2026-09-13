"""Standard-library tests. Run beside original and diagnostic receivers."""
import csv
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class ReceiverDiagnosticTests(unittest.TestCase):
    def test_hash_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            shutil.copy(HERE / 'udp_receiver_diagnostic.py', tmp)
            (tmp / 'udp_receiver.py').write_text('# Wrong original\n')
            p = subprocess.run([sys.executable, str(tmp / 'udp_receiver_diagnostic.py'), '--check'], capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('SHA256 differs', p.stderr)
            self.assertFalse((tmp / 'logs_diagnostic').exists())

    def test_loopback_and_injected_parse_delay(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in ['udp_receiver.py', 'udp_receiver_diagnostic.py']:
                shutil.copy(HERE / name, tmp)
            (tmp / 'harness.py').write_text('''import time
import udp_receiver
import udp_receiver_diagnostic as diag
original = udp_receiver.parse_data_packet
def delayed(message):
    packet = original(message)
    if packet.seq_global == 201:
        time.sleep(0.11)
    return packet
udp_receiver.parse_data_packet = delayed
raise SystemExit(diag.main())
''')
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            output = tmp / 'output'
            log = (tmp / 'console.txt').open('w+')
            proc = subprocess.Popen([sys.executable, '-u', str(tmp / 'harness.py'), '--host', '127.0.0.1', '--port', str(port), '--max-valid-packets', '401', '--output-root', str(output)], stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    log.seek(0)
                    if 'Listening on' in log.read():
                        break
                    if proc.poll() is not None:
                        self.fail('Receiver exited before ready')
                    time.sleep(.02)
                else:
                    self.fail('Receiver startup timeout')
                time.sleep(.6)  # Exercise a socket timeout event.
                seqs = list(range(1, 201)) + [202, 201] + list(range(203, 401)) + [400]
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.sendto(b'INVALID', ('127.0.0.1', port))
                    for seq in seqs:
                        msg = f'DATA,1,test_session,test_run,{seq},{seq},GYRO,{seq*8000000},{seq*8000000+100},{seq*8000000+200},0.1,-0.2,0.3,3'
                        sender.sendto(msg.encode(), ('127.0.0.1', port))
                        time.sleep(.002)
                self.assertEqual(proc.wait(timeout=15), 0)
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                log.close()
            run = next(output.iterdir())
            meta = json.loads((run / 'run.json').read_text())
            summary = meta['summary']
            self.assertEqual(summary['valid_packets'], 401)
            self.assertEqual(summary['invalid_packets'], 1)
            stats = summary['sessions']['test_session']
            self.assertEqual(stats['unique_received'], 400)
            self.assertEqual(stats['missing_within_received_range'], 0)
            self.assertEqual(stats['duplicate'], 1)
            self.assertEqual(stats['out_of_order'], 1)
            with (run / 'raw.csv').open() as f:
                raw = list(csv.DictReader(f))
            with (run / 'timing.csv').open() as f:
                timing = list(csv.DictReader(f))
            valid = [e for e in timing if e['status'] == 'valid']
            self.assertEqual(len(raw), len(valid))
            self.assertTrue(any(e['status'] == 'timeout' for e in timing))
            self.assertEqual(sum(bool(e['flush_before_ns']) for e in valid), 2)
            for r, e in zip(raw, valid):
                self.assertEqual(r['seq_global'], e['seq_global'])
                self.assertEqual(r['pc_receive_monotonic_ns'], e['recv_after_ns'])
                chain = ['recv_before_ns', 'recv_after_ns', 'parse_before_ns', 'parse_after_ns', 'stats_before_ns', 'stats_after_ns', 'write_before_ns', 'write_after_ns', 'cycle_end_ns']
                ts = [int(e[k]) for k in chain]
                self.assertEqual(ts, sorted(ts))
            delayed = next(e for e in valid if e['seq_global'] == '201')
            self.assertGreaterEqual(int(delayed['parse_after_ns']) - int(delayed['parse_before_ns']), 100_000_000)


if __name__ == '__main__':
    unittest.main(verbosity=2)

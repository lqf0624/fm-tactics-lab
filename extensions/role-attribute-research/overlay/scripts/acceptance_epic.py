"""Run Epic acceptance on a matching local game installation; preserve evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request

from repackage_release import EPIC_DLL


def process_rows():
    command = ('Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,'
               'CreationDate | ConvertTo-Json -Compress')
    output = subprocess.check_output(['powershell.exe', '-NoProfile', '-Command', command],
        creationflags=subprocess.CREATE_NO_WINDOW)
    return json.loads(output.decode('utf-8-sig'))


def descendants(rows, root):
    found = {root}
    while True:
        expanded = found | {r['ProcessId'] for r in rows if r['ParentProcessId'] in found}
        if expanded == found:
            return {r['ProcessId']: r['CreationDate'] for r in rows if r['ProcessId'] in found}
        found = expanded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--game-root', type=Path, required=True)
    parser.add_argument('--platform', choices=('epic', 'steam'), default='epic',
                        help='Steam checks shared workflows only, never Epic compatibility')
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix='fm27-epic-acceptance-'))
    report = {'status': 'running', 'platform': args.platform, 'checks': [], 'data_dir': str(folder),
              'exe_sha256': hashlib.sha256(args.exe.read_bytes()).hexdigest()}
    child, base = None, None
    print('Evidence directory: ' + str(folder), flush=True)

    def api(path, data=None):
        request = urllib.request.Request(base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    def passed(name, **facts):
        report['checks'].append(dict(name=name, status='passed', **facts))
        print('PASS ' + name, flush=True)

    def start(label):
        nonlocal child, base
        data = folder / label
        child = subprocess.Popen([str(args.exe.resolve()), '--test-lifecycle', '--no-browser',
            '--data-dir', str(data), '--game-root', str(args.game_root.resolve())],
            creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 90
        while not (data / 'url.txt').exists():
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Startup failed: ' + str(data))
            time.sleep(.5)
        base = (data / 'url.txt').read_text(encoding='utf-8-sig')
        status = api('/api/status')['engine_compatibility']
        assert status['actual_dll_sha256'] == report['game_dll_sha256'], status
        assert status['compatible'] and status['can_simulate'], status
        return api('/api/defaults')

    def wait_job(job_id, predicate, timeout=900):
        deadline = time.monotonic() + timeout
        last_log = 0
        while time.monotonic() < deadline:
            job = api('/api/jobs/' + job_id)
            if predicate(job):
                return job
            if job['status'] in ('complete', 'error', 'cancelled', 'interrupted'):
                raise RuntimeError('Unexpected terminal state: ' + str((job_id, job['status'], job.get('error'))))
            if time.monotonic() - last_log > 15:
                print(job_id, job['status'], job['completed'], '/', job['total'], flush=True)
                last_log = time.monotonic()
            time.sleep(.2)
        raise TimeoutError(job_id)

    def keys(job):
        return {(r['variant'], r['seed']) for r in job['runs']}

    def cancel_resume(job_id, label):
        assert api('/api/cancel', {'id': job_id})['accepted']
        stopped = wait_job(job_id, lambda j: j['status'] == 'cancelled', 120)
        kept = keys(stopped)
        assert len(kept) == stopped['completed']
        assert api('/api/resume', {'id': job_id, 'workers': 2})['id'] == job_id
        passed(label, completed_preserved=len(kept), job_id=job_id)
        return kept

    def shutdown(force=False):
        nonlocal child, base
        owned = descendants(process_rows(), child.pid)
        assert len(owned) >= 3, 'No active native worker captured for exit test'
        if force:
            child.kill()
        else:
            try:
                api('/api/desktop-shutdown', {})
            except OSError:
                pass
        child.wait(timeout=45)
        deadline = time.monotonic() + 15
        while True:
            remaining = [r['ProcessId'] for r in process_rows()
                         if r['ProcessId'] in owned and owned[r['ProcessId']] == r['CreationDate']]
            if not remaining:
                break
            if time.monotonic() > deadline:
                raise RuntimeError('Test descendants remain: ' + str(remaining))
            time.sleep(.5)
        passed('forced_exit_cleanup' if force else 'graceful_exit_cleanup', tracked_processes=len(owned))
        child, base = None, None

    try:
        dll = args.game_root / 'fm_Data/Plugins/x86_64/game_plugin.dll'
        if not dll.is_file() or not (args.game_root / 'shared/data/simatch.fmf').is_file():
            report['status'] = 'blocked'
            raise RuntimeError('A complete local Epic FM27 installation is required')
        digest = hashlib.sha256(dll.read_bytes()).hexdigest()
        report['game_dll_sha256'] = digest
        if args.platform == 'epic' and digest != EPIC_DLL:
            report['status'] = 'blocked'
            raise RuntimeError('Game DLL does not match the supported Epic build: ' + digest)
        scenario = start('normal')
        job_id = api('/api/run', dict(scenario=scenario, seeds=[730], workers=1, event_details=False))['id']
        job = wait_job(job_id, lambda j: j['status'] == 'complete')
        assert job['completed'] == job['total'] == 1
        passed('complete_native_match', job_id=job_id)
        request = dict(scenario=scenario, side=0, slots=[10], research=True,
            exploration_count=4, attribute_scope='roles', opponents='current',
            seeds=list(range(740,752)), workers=2, event_details=False,
            validation_mode='two_stage', profile_mode='current', attribute_increase=3,
            candidate_threshold=0, strong_threshold=.05, candidate_limit=2,
            recommendation_limit=2, stable_min_pairs=8)
        job_id = api('/api/run-attribute-screen', request)['id']
        wait_job(job_id, lambda j: j['status'] == 'running' and j['completed'] >= 2)
        kept = cancel_resume(job_id, 'cancel_resume_exploration')
        wait_job(job_id, lambda j: j['status'] == 'running' and j.get('attribute_stage') == 'validation')
        kept |= cancel_resume(job_id, 'cancel_resume_validation')
        job = wait_job(job_id, lambda j: j['status'] == 'complete')
        assert kept.issubset(keys(job)) and len(keys(job)) == len(job['runs']) == job['total']
        assert job['attribute_screen']['selection_policy'] == 'dual_v1'
        rows = job['attribute_report']
        assert len(rows) == 4 and any(r['selected'] for r in rows)
        assert all(r['exploration']['n'] == 4 and r['n'] == (8 if r['selected'] else 0) for r in rows)
        passed('two_stage_research', job_id=job_id, completed=job['completed'])
        for force in (False, True):
            if force:
                scenario = start('forced')
            batch = api('/api/run', dict(scenario=scenario, seeds=list(range(800,900)), workers=2, event_details=False))['id']
            wait_job(batch, lambda j: j['status'] == 'running' and j['completed'] >= 1)
            shutdown(force)
        report['status'] = 'passed'
    except Exception as error:
        if report['status'] != 'blocked':
            report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        if child and child.poll() is None:
            # Only stop this test's launcher and its owned process tree.
            child.kill()
            child.wait(timeout=15)
        (folder / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
        print('Report: ' + str(folder / 'acceptance.json'), flush=True)


if __name__ == '__main__':
    main()

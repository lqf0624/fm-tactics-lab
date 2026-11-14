"""Opt-in native smoke test with isolated data and the packaged runtime."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import time
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--game-root', type=Path, required=True)
    args = parser.parse_args()
    folder = Path(tempfile.mkdtemp(prefix='fm27-research-smoke-'))
    print('Test data: ' + str(folder), flush=True)
    child = subprocess.Popen([str(args.exe.resolve()), '--test-lifecycle', '--no-browser',
        '--data-dir', str(folder), '--game-root', str(args.game_root.resolve())],
        creationflags=subprocess.CREATE_NO_WINDOW)
    base = None

    def api(path, data=None):
        request = urllib.request.Request(base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    try:
        deadline = time.monotonic() + 90
        while not (folder / 'url.txt').exists():
            if child.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Startup failed; inspect ' + str(folder))
            time.sleep(.5)
        base = (folder / 'url.txt').read_text(encoding='utf-8-sig')
        status = api('/api/status')
        assert status['engine_compatibility']['can_simulate'], status['engine_compatibility']
        scenario = api('/api/defaults')
        for mode in ('two_stage', 'full'):
            request = dict(scenario=scenario, side=0, slots=[10], research=True,
                exploration_count=4, attribute_scope='roles', opponents='current',
                seeds=list(range(740,746)), workers=2, event_details=False,
                validation_mode=mode, profile_mode='standard', standard_levels=[8,16],
                attribute_increase=3, candidate_threshold=0, strong_threshold=.05,
                candidate_limit=1, recommendation_limit=1, stable_min_pairs=8)
            job_id = api('/api/run-attribute-screen', request)['id']
            deadline = time.monotonic() + 600
            last = None
            while True:
                job = api('/api/jobs/' + job_id)
                progress = (job['status'], job['completed'], job['total'])
                if progress != last:
                    print(mode, job_id, progress, flush=True)
                    last = progress
                if job['status'] in ('complete', 'error', 'cancelled', 'interrupted'):
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError(job_id)
                time.sleep(2)
            assert job['status'] == 'complete', job.get('error', job['status'])
            assert job['completed'] == job['total']
            assert job['attribute_screen']['selection_policy'] == 'dual_v1'
            rows = job['attribute_report']
            assert len(rows) == 4
            assert all(row['exploration']['n'] == 4 for row in rows)
            assert all(row['recommendation_tier'] != 'stable' for row in rows)
            if mode == 'full':
                assert all(row['n'] == 2 for row in rows)
            else:
                assert sum(row['selected'] for row in rows) <= 2
                assert all(row['n'] == (2 if row['selected'] else 0) for row in rows)
            print('PASS', mode, job['completed'], 'matches', flush=True)
    finally:
        if base:
            try:
                api('/api/desktop-shutdown', {})
            except OSError:
                pass
        try:
            child.wait(timeout=30)
        except subprocess.TimeoutExpired:
            # Closing this test launcher also closes its Job Object worker tree.
            child.kill()
            child.wait(timeout=10)
        print('Test launcher exited; logs preserved in ' + str(folder), flush=True)


if __name__ == '__main__':
    main()

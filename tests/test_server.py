import asyncio
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from Server.app import create_app, ROOT


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.spa = self.root / 'spa'
        self.spa.mkdir()
        (self.spa / 'index.html').write_text('<h1>SPA</h1>')
        (self.spa / 'asset.js').write_text('/* asset */')
        self.app = create_app(dict(TESTING=True, DATA_CACHE=self.cache, SPA_DIR=self.spa))
        self.client = self.app.test_client()

    def fixtures(self):
        shutil.copytree(ROOT / 'Pipeline/Mock_Event', self.cache / 'events')
        path = next((self.cache / 'events').glob('*.json'))
        return json.loads(path.read_text())

    def wait_run(self, run_id):
        for _ in range(200):
            status = self.client.get(f'/api/pipeline/status/{run_id}').json
            if status['state'] != 'running':
                return status
            time.sleep(0.01)
        self.fail('Run did not finish')

    def test_empty_routes_and_spa(self):
        self.assertEqual(self.client.get('/api/health').json, {'ok': True})
        for route in ('events', 'alerts', 'tracked'):
            self.assertEqual(self.client.get('/api/' + route).json, [])
        self.assertEqual(self.client.get('/api/watchlist').json, {'tickers': []})
        for path in ('/', '/events/example'):
            response = self.client.get(path)
            self.assertIn(b'SPA', response.data)
            response.close()
        response = self.client.get('/asset.js')
        self.assertIn(b'asset', response.data)
        response.close()
        for route in ('/api/missing', '/api', '/api/events/missing', '/api/pipeline/status/x', '/api/pipeline/stream/x'):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 404)
            self.assertIn('error', response.json)

    def test_event_alerts_tracking_and_refresh(self):
        event = self.fixtures()
        event_id = event['event']['event_id']
        impacts = event['impacts']
        ticker = impacts[0]['ticker']
        self.assertEqual(self.client.get('/api/events/' + event_id).json, event)
        for impact in impacts[:2]:
            self.client.post('/api/watchlist', json={'ticker': impact['ticker'].lower()})
        self.client.post('/api/watchlist', json={'ticker': ticker})
        self.assertEqual(len(self.client.get('/api/watchlist').json['tickers']), 2)
        alerts = self.client.get('/api/alerts').json
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]['affected_count'], len(impacts))
        self.assertEqual({x['relation'] for x in alerts[0]['matched']}, {x['relation'] for x in impacts[:2]})
        summaries = self.client.get('/api/events').json
        top = max(impacts, key=lambda x: abs(x['study']['car_pct']))
        summary = next(x for x in summaries if x['event_id'] == event_id)
        self.assertEqual(summary['top_impact']['ticker'], top['ticker'])
        for _ in range(2):
            records = self.client.post('/api/tracked', json={'event_id': event_id, 'ticker': ticker.lower()}).json
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]['tracked_at'].endswith('Z'))
        self.assertEqual(json.loads((self.cache / 'tracked.json').read_text()), records)
        self.assertEqual(self.client.delete(f'/api/tracked/{event_id}/{ticker}').json, [])
        self.assertEqual(self.client.post('/api/tracked', json={'event_id': event_id, 'ticker': 'UNKNOWN'}).status_code, 400)
        called = []
        self.app.config['EVENT_REFRESH'] = lambda value: called.append(value) or event
        self.assertEqual(self.client.post(f'/api/events/{event_id}/refresh').json, event)
        self.assertEqual(called, [event_id])
        self.client.delete('/api/watchlist/' + ticker)
        self.assertNotIn(ticker, self.client.get('/api/watchlist').json['tickers'])

    def test_invalid_requests(self):
        for data in ([], None, {'ticker': '../oops'}, {'ticker': ''}, {'ticker': 123}):
            self.assertEqual(self.client.post('/api/watchlist', json=data).status_code, 400)
        for data in ({'days_back': True}, {'days_back': 0}, {'days_back': 1.5},
                     {'event_types': []}, {'event_types': ['invalid']}, {'event_types': [{}]}):
            self.assertEqual(self.client.post('/api/pipeline/run', json=data).status_code, 400)
        self.assertEqual(self.client.post('/api/pipeline/run', data='{', content_type='application/json').status_code, 400)

    def test_run_lock_replay_and_polling(self):
        release = threading.Event()
        self.addCleanup(release.set)
        received = []
        async def pipeline(params):
            received.append(params)
            yield dict(type='progress', completed=0, total=6, stage=None, stage_label=None)
            while not release.is_set():
                await asyncio.sleep(0.005)
            yield dict(type='info', message='Found events', tag='info')
            yield dict(type='progress', completed=6, total=6, stage='EventWriter', stage_label='Saving results')
            yield dict(type='result', success=True, event_ids=['example'], exit_reason=None)
        self.app.config['PIPELINE_STREAM'] = pipeline
        run_id = self.client.post('/api/pipeline/run').json['run_id']
        self.assertEqual(self.client.post('/api/pipeline/run').status_code, 409)
        release.set()
        status = self.wait_run(run_id)
        self.assertEqual(status['state'], 'done')
        self.assertEqual(status['completed'], 6)
        self.assertEqual(status['last_message'], 'Found events')
        self.assertEqual(status['event_ids'], ['example'])
        self.assertEqual(received[0]['days_back'], 3)
        self.assertNotIn('other', received[0]['event_types'])
        url = f'/api/pipeline/stream/{run_id}'
        first = self.client.get(url)
        self.assertEqual(first.headers['X-Accel-Buffering'], 'no')
        self.assertEqual(first.data, self.client.get(url).data)
        frames = [json.loads(line[6:]) for line in first.text.splitlines() if line.startswith('data: ')]
        self.assertEqual([x['seq'] for x in frames], list(range(4)))
        self.assertEqual([x['type'] for x in frames], ['progress', 'info', 'progress', 'done'])
        replay = self.client.get(url, headers={'Last-Event-ID': '2'}).text
        self.assertIn('id: 3', replay)
        self.assertNotIn('id: 2', replay)
        self.assertEqual(self.client.get(url, headers={'Last-Event-ID': '3'}).data, b'')
        self.assertEqual(self.client.get(url, headers={'Last-Event-ID': 'oops'}).status_code, 400)
        self.assertEqual(self.client.post('/api/pipeline/run').status_code, 200)
        self.wait_run(next(reversed(self.app.extensions['pipeline_runs'])))

    def test_early_failure_crash_and_missing_result(self):
        async def early(params):
            yield dict(type='result', success=True, event_ids=[], exit_reason='Nothing new')
        async def failure(params):
            yield dict(type='result', success=False, error_message='Upstream failed')
        async def crash(params):
            raise RuntimeError('boom')
            yield
        async def missing(params):
            yield dict(type='info', message='hello', tag='info')
        for pipeline, state, message in ((early, 'done', 'Nothing new'), (failure, 'error', 'Upstream failed'),
                                         (crash, 'error', 'Pipeline crashed'), (missing, 'error', 'Pipeline crashed')):
            self.app.config['PIPELINE_STREAM'] = pipeline
            run_id = self.client.post('/api/pipeline/run', json={}).json['run_id']
            with patch.object(self.app.logger, 'exception'):
                status = self.wait_run(run_id)
            self.assertEqual(status['state'], state)
            self.assertEqual(status['exit_reason'] if state == 'done' else status['error_message'], message)
            frames = self.app.extensions['pipeline_runs'][run_id]['frames']
            self.assertEqual(sum(f['type'] in ('done', 'error') for f in frames), 1)


if __name__ == '__main__':
    unittest.main()

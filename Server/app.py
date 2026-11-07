"""JSON API and SPA host. Run with python -m Server.app from the repo root."""
import asyncio
import importlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, Response, abort, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
from werkzeug.utils import safe_join

ROOT = Path(__file__).resolve().parent.parent
EVENT_TYPES = ['merger', 'breach', 'recall', 'outage', 'lawsuit', 'regulation']


def sse_format(frame):
    return f"id: {frame['seq']}\nevent: {frame['type']}\ndata: {json.dumps(frame, ensure_ascii=False)}\n\n"


def create_app(config=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_mapping(DATA_CACHE=ROOT / 'Data_Cache', SPA_DIR=ROOT / 'Server/static_spa',
                            PIPELINE_STREAM=None, EVENT_REFRESH=None)
    app.config.update(config or {})
    cache = Path(app.config['DATA_CACHE'])
    storage_lock = threading.Lock()
    run_lock = threading.RLock()
    runs = {}
    app.extensions['pipeline_runs'] = runs

    def read_list(name):
        try:
            return json.loads((cache / f'{name}.json').read_text())
        except FileNotFoundError:
            return []

    def write_list(name, value):
        cache.mkdir(parents=True, exist_ok=True)
        path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=cache,
                                             suffix='.tmp', delete=False) as file:
                path = file.name
                json.dump(value, file, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(path, cache / f'{name}.json')
        finally:
            if path and os.path.exists(path):
                os.unlink(path)

    def event_path(event_id):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[a-z0-9-]+', event_id):
            abort(404, description='Unknown event_id')
        return cache / 'events' / f'{event_id}.json'

    def read_event(event_id):
        try:
            return json.loads(event_path(event_id).read_text())
        except FileNotFoundError:
            abort(404, description='Unknown event_id')

    def body(optional=False):
        if optional and not request.get_data():
            return {}
        if not request.is_json:
            abort(400, description='Expected a JSON object')
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400, description='Expected a JSON object')
        return data

    def ticker(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^=\-]{0,31}', value.strip().upper()):
            abort(400, description='Invalid ticker')
        return value.strip().upper()

    def pipeline_function(key, name):
        return app.config[key] or getattr(importlib.import_module('Pipeline.main'), name)

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def server_error(error):
        app.logger.exception('Request failed')
        return jsonify(error='Internal server error'), 500

    @app.get('/api/health')
    def health():
        return jsonify(ok=True)

    def summaries(alerts=False):
        with storage_lock:
            watchlist = set(read_list('watchlist'))
        result = []
        for path in (cache / 'events').glob('*.json'):
            data = json.loads(path.read_text())
            impacts = data['impacts']
            top = max(impacts, key=lambda item: abs(item['study']['car_pct']))
            matched = []
            for item in impacts:
                if item['ticker'] not in watchlist:
                    continue
                study = item['study']
                daily = study.get('daily') or []
                matched.append(dict(ticker=item['ticker'], relation=item['relation'],
                                    car_pct=study['car_pct'], days_after=study.get('days_after'),
                                    prices_through=daily[-1].get('date') if daily else None,
                                    is_significant=study['is_significant']))
            summary = {key: data['event'][key] for key in
                       ('event_id', 'event_type', 'headline', 'event_date')}
            summary.update(status=data['status'], affected_count=len(impacts),
                           top_impact=dict(ticker=top['ticker'], car_pct=top['study']['car_pct'],
                                           is_significant=top['study']['is_significant']),
                           touches_watchlist=bool(matched))
            if alerts:
                if not matched:
                    continue
                summary['matched'] = matched
            result.append(summary)
        return jsonify(sorted(result, key=lambda item: item['event_date'], reverse=True))

    app.add_url_rule('/api/events', 'events', summaries)
    app.add_url_rule('/api/alerts', 'alerts', lambda: summaries(True))

    @app.get('/api/events/<event_id>')
    def detail(event_id):
        return jsonify(read_event(event_id))

    @app.post('/api/events/<event_id>/refresh')
    def refresh(event_id):
        read_event(event_id)
        callback = pipeline_function('EVENT_REFRESH', 'refresh_event')
        try:
            result = callback(event_id) if app.config['EVENT_REFRESH'] else callback(event_id, data_cache=cache)
        except ValueError as error:
            abort(422, description=str(error))
        return jsonify(result)

    @app.route('/api/watchlist', methods=['GET', 'POST'])
    def watchlist():
        value = ticker(body().get('ticker')) if request.method == 'POST' else None
        with storage_lock:
            values = read_list('watchlist')
            if value and value not in values:
                values.append(value)
                write_list('watchlist', values)
        return jsonify(tickers=values)

    @app.delete('/api/watchlist/<value>')
    def remove_watchlist(value):
        value = ticker(value)
        with storage_lock:
            values = [item for item in read_list('watchlist') if item != value]
            write_list('watchlist', values)
        return jsonify(tickers=values)

    @app.route('/api/tracked', methods=['GET', 'POST'])
    def tracked():
        record = None
        if request.method == 'POST':
            data = body()
            event_id = data.get('event_id')
            if not isinstance(event_id, str):
                abort(400, description='event_id is required')
            value = ticker(data.get('ticker'))
            event = read_event(event_id)
            if value not in [item['ticker'] for item in event['impacts']]:
                abort(400, description='Ticker is not affected by this event')
            record = dict(event_id=event_id, ticker=value,
                          tracked_at=datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'))
        with storage_lock:
            values = read_list('tracked')
            if record and not any(item['event_id'] == record['event_id'] and
                                  item['ticker'] == record['ticker'] for item in values):
                values.append(record)
                write_list('tracked', values)
        return jsonify(values)

    @app.delete('/api/tracked/<event_id>/<value>')
    def remove_tracked(event_id, value):
        event_path(event_id)
        value = ticker(value)
        with storage_lock:
            values = [item for item in read_list('tracked')
                      if (item['event_id'], item['ticker']) != (event_id, value)]
            write_list('tracked', values)
        return jsonify(values)

    def append(run, frame):
        with run_lock:
            if run['state'] != 'running':
                return
            frame = dict(frame, seq=len(run['frames']))
            run['frames'].append(frame)
            run['latest'] = frame
            if frame['type'] in ('done', 'error'):
                run['state'] = frame['type']

    def worker(run, params):
        async def consume():
            if not app.config['PIPELINE_STREAM']:
                params['data_cache'] = cache
            stream = pipeline_function('PIPELINE_STREAM', 'stream_pipeline')(params)
            try:
                async for event in stream:
                    if event['type'] == 'result':
                        if event['success']:
                            event_ids = list(dict.fromkeys(event.get('event_ids', [])))
                            frame = dict(type='done', success=True, event_ids=event_ids,
                                         new_count=sum(event_id not in run['existing_ids'] for event_id in event_ids))
                            if event.get('exit_reason') is not None:
                                frame['exit_reason'] = event['exit_reason']
                        else:
                            frame = dict(type='error', message=event['error_message'])
                        append(run, frame)
                        return
                    if event['type'] not in ('info', 'progress'):
                        raise ValueError('Unknown pipeline event type')
                    append(run, event)
            finally:
                await stream.aclose()
        try:
            asyncio.run(consume())
        except Exception:
            app.logger.exception('Pipeline crashed')
        finally:
            append(run, dict(type='error', message='Pipeline crashed'))

    @app.post('/api/pipeline/run')
    def start_run():
        data = body(optional=True)
        types = data.get('event_types', EVENT_TYPES.copy())
        days = data.get('days_back', 30)
        if (not isinstance(types, list) or not types or
                any(not isinstance(item, str) or item not in EVENT_TYPES + ['other'] for item in types)):
            abort(400, description='event_types must be a non-empty list of valid event types')
        if type(days) is not int or days < 1:
            abort(400, description='days_back must be a positive integer')
        with run_lock:
            if any(run['state'] == 'running' for run in runs.values()):
                abort(409, description='A pipeline run is already running')
            run_id = str(uuid4())
            run = dict(frames=[], state='running', latest=None,
                       existing_ids={path.stem for path in (cache / 'events').glob('*.json')})
            runs[run_id] = run
            try:
                threading.Thread(target=worker, args=(run, dict(event_types=types, days_back=days)),
                                 daemon=True).start()
            except Exception:
                append(run, dict(type='error', message='Pipeline crashed'))
                raise
        return jsonify(run_id=run_id)

    def get_run(run_id):
        with run_lock:
            if run_id not in runs:
                abort(404, description='Unknown run_id')
            return runs[run_id]

    @app.get('/api/pipeline/status/<run_id>')
    def status(run_id):
        run = get_run(run_id)
        with run_lock:
            result = dict(run_id=run_id, state=run['state'], completed=0, total=6,
                          stage_label=None, last_message=None, event_ids=[],
                          exit_reason=None, error_message=None)
            for frame in run['frames']:
                if frame['type'] == 'progress':
                    result.update({key: frame[key] for key in ('completed', 'total', 'stage_label')})
                elif frame['type'] == 'info':
                    result['last_message'] = frame['message']
                elif frame['type'] == 'done':
                    result.update(event_ids=frame['event_ids'], new_count=frame['new_count'],
                                  exit_reason=frame.get('exit_reason'))
                elif frame['type'] == 'error':
                    result['error_message'] = frame['message']
        return jsonify(result)

    @app.get('/api/pipeline/stream/<run_id>')
    def stream(run_id):
        run = get_run(run_id)
        last = request.headers.get('Last-Event-ID')
        if last is not None and not re.fullmatch(r'-1|[0-9]+', last):
            abort(400, description='Invalid Last-Event-ID')
        cursor = int(last) + 1 if last is not None else 0

        def generate():
            nonlocal cursor
            sent = time.monotonic()
            while True:
                with run_lock:
                    frames = run['frames'][cursor:]
                    finished = run['state'] != 'running'
                for frame in frames:
                    yield sse_format(frame)
                    cursor = frame['seq'] + 1
                    sent = time.monotonic()
                    if frame['type'] in ('done', 'error'):
                        return
                if finished:
                    return
                if time.monotonic() - sent >= 15:
                    yield ': ping\n\n'
                    sent = time.monotonic()
                time.sleep(0.2)
        return Response(generate(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def spa(path):
        if path == 'api' or path.startswith('api/'):
            abort(404, description='Unknown API path')
        folder = Path(app.config['SPA_DIR']).resolve()
        joined = safe_join(str(folder), path)
        if joined and Path(joined).is_file() and Path(joined).resolve().is_relative_to(folder):
            return send_from_directory(folder, path)
        if not (folder / 'index.html').is_file():
            abort(404, description='SPA build not found; build the frontend into Server/static_spa')
        return send_from_directory(folder, 'index.html')

    return app


app = create_app()

if __name__ == '__main__':
    app.run(port=5000)

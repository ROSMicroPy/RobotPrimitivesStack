"""Native-REPL launcher, installed as slide_nodes.py. Requires _thread.

Imports and manifest reads happen before the worker starts.
Only the worker thread constructs runtime objects and runs asyncio. The REPL exchanges
requests/results through a lock; it never schedules tasks across threads.
"""
import _thread
import time
import sys

_BASE = __file__.rsplit('/', 1)[0] if '/' in __file__ else '.'
_session = None


def _pause():
    time.sleep(0.01)


def _prepare_document(path, log):
    # Imports may recurse through the filesystem and compiler. Keep that work
    # off the ESP32 worker's C stack, including selected drivers and apps.
    from rpstack.node_runtime.manifest import load_document, load_entry_point, ServiceManifest
    document = load_document(path)
    entries = []
    for spec in document.get('services', {}).values():
        manifest = ServiceManifest(document['components'][spec['component']])
        entries.append(manifest.entry_point)
        implementation = spec.get('implementation')
        if implementation:
            entries.append(manifest.implementation(implementation)['entry_point'])
    for spec in document.get('runtime', []) + document.get('apps', []):
        entries.append(spec['entry_point'])
    for spec in document.get('signals', {}).get('transports', []):
        entries.append(spec['entry_point'])
    for entry in entries:
        log('importing ' + entry)
        load_entry_point(entry)
    return document


class _Session:
    def __init__(self, role, provider_path, client_path, verbose, gateway_path):
        self.verbose = verbose
        self.gateway_path = gateway_path
        self.gateway_document = None
        self.provider_document = None
        self.client_document = None
        self.role = role
        self.provider_path = provider_path
        self.client_path = client_path
        self.lock = _thread.allocate_lock()
        self.shared = {'state': 'starting', 'error': None, 'finished': False,
                       'stop': False, 'cancel_demo': False, 'job': None,
                       'node1': 'starting' if role == 'slide' else 'remote'}

    def log(self, message):
        if self.verbose:
            print('[slide_nodes] ' + message)

    def prepare(self):
        self.log('loading runtime on foreground stack')
        from rpstack.support import asyncio
        from rpstack.node_runtime import NodeRuntime
        self.asyncio = asyncio
        self.node_factory = NodeRuntime
        if self.role == 'slide':
            self.log('loading slide manifest')
            self.provider_document = _prepare_document(self.provider_path, self.log)
        self.log('loading client manifest')
        self.client_document = _prepare_document(self.client_path, self.log)
        if self.role == 'client':
            self.log('loading client gateway manifest')
            self.gateway_document = _prepare_document(self.gateway_path, self.log)

    def read(self):
        with self.lock:
            return dict(self.shared)

    def update(self, **values):
        with self.lock:
            self.shared.update(values)

    def worker(self):
        try:
            asyncio = self.asyncio
            try:
                asyncio.run(self.run())
            finally:
                # MicroPython has one global loop. Reset only after all nodes
                # have shut down, so another start() gets a clean scheduler.
                if sys.implementation.name == "micropython":
                    asyncio.new_event_loop()
        except BaseException as error:
            self.update(error=str(error) or type(error).__name__)
        finally:
            with self.lock:
                job = self.shared['job']
                if job is not None and not job['done']:
                    job.update(done=True, error=self.shared['error'] or 'node loop stopped')
                self.shared['state'] = 'failed' if self.shared['error'] else 'stopped'
                self.shared['finished'] = True

    def slide_status(self, provider):
        result = provider.instance('slide').status()
        result['step_delay_us'] = provider.instance('motor').status().get('step_delay_us')
        return result

    async def run(self):
        asyncio = self.asyncio
        provider = None
        gateway = None
        task = None
        active_job = None
        try:
            if self.role == 'slide':
                self.log('initializing slide hardware and radio')
                provider = self.node_factory(self.provider_document)
                await provider.boot()
                gateway = provider
            else:
                gateway = self.node_factory(self.gateway_document)
                await gateway.boot()
            http = gateway.runtime_instances.get('http')
            wifi = gateway.runtime_instances.get('wifi')
            if http is not None:
                address = wifi.wlan.ifconfig()[0] if wifi and wifi.wlan else '127.0.0.1'
                url = 'http://' + address + ':' + str(http.server.port)
                self.update(gateway_url=url)
                self.log('RobotArchitect gateway: ' + url)
            if provider is not None:
                self.update(slide=self.slide_status(provider))
                self.log('pulse mode: ' + str(self.read()['slide'].get('pulse_mode')) +
                         ', step_delay_us: ' + str(self.read()['slide']['step_delay_us']))
                self.log('slide is stationary; call calibrate() before demo()')
            self.log('ready (' + self.role + ')')
            self.update(state='running', node1=provider.state if provider else 'remote')
            while not self.read()['stop']:
                state = self.read()
                if state['job'] is not None and state['job'] is not active_job:
                    active_job = state['job']
                    task = asyncio.create_task(self.move(active_job))
                if state['cancel_demo']:
                    if task is not None:
                        task.cancel()
                    self.update(cancel_demo=False)
                if provider is not None:
                    self.update(node1=provider.state, slide=self.slide_status(provider))
                if gateway is not None and gateway.state == 'failed':
                    raise RuntimeError('node1 failed; stop and restart after correcting the cause')
                await asyncio.sleep(0.01)
        finally:
            self.update(state='stopping')
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            if gateway is not None and gateway is not provider:
                await gateway.shutdown()
            if provider is not None:
                await provider.shutdown()
                self.update(node1=provider.state)

    async def move(self, job):
        asyncio = self.asyncio
        client = None
        result = None
        error = None
        try:
            # At most one demo is active. Copy only the app configuration that
            # this launch changes; retain the preloaded manifest as a template.
            document = dict(self.client_document)
            document["apps"] = [dict(spec) for spec in document["apps"]]
            document["apps"][0]["config"] = dict(document["apps"][0].get("config", {}))
            config = document['apps'][0].setdefault('config', {})
            config.update(position_mm=job['position_mm'], timeout_s=job['timeout_s'],
                          command=job['command'], steps=job['steps'],
                          min_mm=job['min_mm'], max_mm=job['max_mm'])
            client = self.node_factory(document)
            await client.boot()
            await client.wait()
            result = client.apps['move'].received[-1]['payload']
        except asyncio.CancelledError:
            error = 'demo cancelled'
        except Exception as exc:
            error = str(exc) or type(exc).__name__
        finally:
            try:
                if client is not None:
                    await client.shutdown()
            except Exception as exc:
                error = str(exc) or type(exc).__name__
            with self.lock:
                job.update(done=True, result=result, error=error)


def start(role="slide", provider_path=None, client_path=None, stack_size=65536, verbose=True, gateway_path=None):
    """Start the slide or client host and return to the native >>> prompt."""
    global _session
    if role not in ("slide", "client"):
        raise ValueError("role must be slide or client")
    if _session is not None and not _session.read()['finished']:
        raise RuntimeError('already started; use status(), demo(), or stop()')
    if type(stack_size) is not int or stack_size < 32768:
        raise ValueError("stack_size must be at least 32768 bytes")
    session = _Session(role, provider_path or _BASE + '/slide_node1.json',
                       client_path or _BASE + '/slide_node2.json', verbose,
                       gateway_path or _BASE + '/slide_client_host.json')
    _session = session
    try:
        session.prepare()
        session.log('starting worker (' + str(stack_size) + ' byte stack)')
        previous_stack_size = _thread.stack_size()
        try:
            _thread.stack_size(stack_size)
            _thread.start_new_thread(session.worker, ())
        finally:
            _thread.stack_size(previous_stack_size)
    except BaseException as error:
        session.update(state='failed', finished=True,
                       error=str(error) or type(error).__name__)
        raise
    try:
        while session.read()['state'] == 'starting':
            _pause()
        state = session.read()
        if state['state'] != 'running':
            while not session.read()['finished']:
                _pause()
            raise RuntimeError(session.read()['error'] or 'node startup failed')
        return status()
    except KeyboardInterrupt:
        session.update(stop=True)
        raise


def demo(position_mm=100, timeout_s=30):
    """Move to an absolute target after explicit calibrate calibration."""
    return _request('move', position_mm=position_mm, timeout_s=timeout_s)


def position(timeout_s=5):
    """Read the slide position without moving; works locally or remotely."""
    return _request('observe', timeout_s=timeout_s)


def set_range(min_mm, max_mm, timeout_s=5):
    """Set the provider's target range until restart, locally or remotely."""
    return _request('set_range', min_mm=min_mm, max_mm=max_mm, timeout_s=timeout_s)


def calibrate(steps=1000, timeout_s=30):
    """Run steps forward then reverse, reporting measured scale and direction."""
    return _request('calibrate', steps=steps, timeout_s=timeout_s)



def _request(command, position_mm=100, steps=1000, timeout_s=30, min_mm=None, max_mm=None):
    session = _session
    if session is None:
        raise RuntimeError('call start() first')
    if type(position_mm) not in (int, float) or not -float('inf') < position_mm < float('inf'):
        raise ValueError('position_mm must be finite and numeric')
    if type(timeout_s) not in (int, float) or not 0 < timeout_s < float('inf'):
        raise ValueError('timeout_s must be finite and positive')
    if type(steps) is not int or steps < 1:
        raise ValueError('steps must be a positive integer')
    job = {'position_mm': position_mm, 'timeout_s': timeout_s,
           'command': command, 'steps': steps, 'min_mm': min_mm, 'max_mm': max_mm,
           'done': False, 'result': None, 'error': None}
    with session.lock:
        state = session.shared
        if state['state'] != 'running' or state['stop']:
            raise RuntimeError('node1 is not running; call start()')
        if state['job'] is not None and not state['job']['done']:
            raise RuntimeError('a demo is already running')
        state['job'] = job
    try:
        while True:
            with session.lock:
                done, result, error = job['done'], job['result'], job['error']
            if done:
                if error is not None:
                    raise RuntimeError(error)
                return result
            _pause()
    except KeyboardInterrupt:
        session.update(cancel_demo=True)
        raise


def status():
    """Return a snapshot without accessing the worker's runtime objects."""
    if _session is None:
        return {'state': 'stopped', 'node1': 'stopped', 'demo': 'idle', 'error': None}
    with _session.lock:
        state = _session.shared
        job = state['job']
        demo_state = 'idle' if job is None else (
            'running' if not job['done'] else ('failed' if job['error'] else 'succeeded'))
        return {'state': state['state'], 'node1': state['node1'],
                'demo': demo_state, 'slide': state.get('slide'),
                'gateway_url': state.get('gateway_url'), 'error': state['error'] or (job['error'] if job else None)}


def stop():
    """Cancel node2 if active, shut down node1, and wait for worker cleanup."""
    if _session is not None:
        _session.update(stop=True)
        while not _session.read()['finished']:
            _pause()
        if _session.read()['error']:
            raise RuntimeError(_session.read()['error'])
    return status()

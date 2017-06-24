Inqubo
============

Inqubo means "process", "series of steps" in zulu.

This is a automated workflow runner / manager


Usage
============

## Branching flow

```python
import asyncio
from inqubo.workflow import  Workflow
from inqubo.decorators import step
from inqubo.runners.simple_runner import SimpleRunner

@step()
async def get_data():
    print('geting data..')
    return ['foo1', 'foo2']

@step()
def process_data(payload):
    print('processing data: {}'.format(payload))
    return ['processed_foo1', 'processed_foo2']

@step()
async def load_data_to_external_system(payload):
    await asyncio.sleep(10)
    print('loaded data to external system: {}'.format(payload))

@step()
def load_data_to_internal_system(payload):
    print('loaded data to internal system: {}'.format(payload))

flow = Workflow('simple')

flow.start(get_data)\
    .then(process_data)\
    .then(load_data_to_external_system, load_data_to_internal_system) # two tasks in parallel

loop = asyncio.get_event_loop()
runner = SimpleRunner(flow, loop)
loop.run_until_complete(runner.trigger('test run'))
loop.close()
```

## Retries

```python
import asyncio
import random

from inqubo.retry_strategies import LimitedRetries, no_retries
from inqubo.workflow import  Workflow
from inqubo.decorators import step
from inqubo.runners.simple_runner import SimpleRunner, SimpleRunFailure


class RandomFailure(Exception):
    def __str__(self):
        return 'random failure'


@step()  # default is 3 retries at 1 second timeout
async def get_data():
    print('geting data..')
    if random.random() > 0.5:
        raise RandomFailure
    return ['foo1', 'foo2']


@step(retry_strategy=LimitedRetries(number_retries=20, retry_timeout=300)) # more attempts for this step
def process_data(payload):
    print('processing data')
    if random.random() > 0.1:
        raise RandomFailure


@step(retry_strategy=no_retries)
async def load_data(payload):
    print('loading data')
    if random.random() > 0.5:
        raise RandomFailure

flow = Workflow('simple')

flow.start(get_data)\
    .then(process_data)\
    .then(load_data) # two tasks in parallel

loop = asyncio.get_event_loop()
runner = SimpleRunner(flow, event_loop=loop)
try:
    loop.run_until_complete(runner.trigger('test run'))
    print('run successful')
except SimpleRunFailure as r:
    print('run failed, errors: {}'.format(r.errors))
loop.close()
```
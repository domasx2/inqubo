import pprint
import asyncio
import logging
import random

from inqubo.retry_strategies import LimitedRetries, no_retries
from inqubo.workflow import  Workflow
from inqubo.decorators import step
from inqubo.runners.simple_runner import SimpleRunner, SimpleRunFailure

logger = logging.getLogger('inqubo')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

pp = pprint.PrettyPrinter(indent=4)


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
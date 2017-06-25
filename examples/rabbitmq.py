import asyncio
import logging
import random

from inqubo.workflow import  Workflow
from inqubo.decorators import step
from inqubo.runners.pika_runner import PikaRunner, PikaClient

logger = logging.getLogger('inqubo')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())


class RandomFailure(Exception):
    def __str__(self):
        return 'random failure'


@step()  # default is 3 retries at 1 second timeout
async def get_data():
    print('geting data...')
    await asyncio.sleep(random.random() * 10)
    if random.random() > 0.5:
        raise RandomFailure
    return ['foo1', 'foo2']


@step() # more attempts for this step
async def process_data(payload):
    print('processing data...')
    await asyncio.sleep(random.random() * 10)
    if random.random() > 0.5:
        raise RandomFailure


@step()
async def load_data_some_system(payload):
    print('loading data to some system...')
    await asyncio.sleep(random.random() * 10)
    if random.random() > 0.5:
        raise RandomFailure

@step()
async def load_data_other_system(payload):
    print('loading data to other system...')
    await asyncio.sleep(random.random() * 10)
    if random.random() > 0.5:
        raise RandomFailure

flow = Workflow('rabbit_workflow')

flow.start(get_data)\
    .then(process_data)\
    .then(load_data_some_system, load_data_other_system)  # two tasks in parallel

loop = asyncio.get_event_loop()

async def main():
    pika_client = PikaClient('amqp://guest:guest@127.0.0.1/', loop)
    pika_runner = PikaRunner(flow, pika_client, loop)
    await pika_runner.start()
    await pika_runner.trigger('test_run_{}'.format(random.randint(0, 100000)))

    while True:
        await asyncio.sleep(100)

try:
    loop.run_until_complete(main())
except KeyboardInterrupt:
        print('bye')
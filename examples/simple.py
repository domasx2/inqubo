import pprint
import asyncio
import logging
from inqubo.workflow import  Workflow
from inqubo.decorators import step
from inqubo.runners.simple_runner import SimpleRunner

logger = logging.getLogger('inqubo')
logger.setLevel(logging.DEBUG)
logger.addHandler(logging.StreamHandler())

pp = pprint.PrettyPrinter(indent=4)

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
runner = SimpleRunner(flow, event_loop=loop)
loop.run_until_complete(runner.trigger('test run'))
loop.close()
Inqubo
============

Inqubo means "process", "series of steps" in zulu.

This is a automated workflow runner / manager.
The idea is define a workflow as a tree (acyclic graph in the future) consisting of atomic actions.
These actions are choreographed using RabbitMQ.
Multiple runners for the same workflow can be started and tasks are automatically balanced.
Retries are implemented using RabbitMQ dead letter exchange feature.


Usage
============

```python
from inqubo.retry_strategies import LimitedRetries, no_retries
from inqubo.workflow import  Workflow
from inqubo.decorators import step

# define stome steps
@step()
async def get_data():
    return await fetch_some_data()


# default is 3 retries with 1 second spacing
@step(retry_strategy=LimitedRetries(number_retries=20, retry_timeout=300))
def process_data(payload):
    return process_the_data(payload)

@step(retry_strategy=no_retries)
async def load_data_to_external_system(payload):
    await upload_it(payload)

@step()
async def load_data_to_internal_system(payload):
    await upload_it_somewhere_else(payload)


#build the workflow
flow = Workflow('simple')

flow.start(get_data)\
    .then(process_data)\
    .then(load_data_to_external_system, load_data_to_internal_system) # two tasks in parallel

# start runner
loop = asyncio.get_event_loop()

async def main():
    # ampq client
    pika_client = PikaClient('amqp://guest:guest@127.0.0.1/', loop)
    
    # setup runner for this flow
    pika_runner = PikaRunner(flow, pika_client, loop)
    
    # set up queues & start listening
    await pika_runner.start()
    
    # trigger a run with a unique id
    await pika_runner.trigger('test_run')

    while True:
        await asyncio.sleep(100)

loop.run_until_complete(main())
```

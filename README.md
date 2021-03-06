Inqubo
============

Inqubo means "process", "series of steps" in zulu.


This is a automated workflow runner / manager.  
The goal was to combine the best features of workflow orchestration & choreography.
Workflows are explicitly defined in code as a tree of atomic tasks. Inqubo automatically choreographs them using RabbitMQ. Tasks are triggered by "success" events from preceeding tasks and themselves emit lifecycle events.

Features
===========


* Workflows are explicitly defined using code
* Easily scalable, work is automatically load balanced between active runners
* It's just a thin layer over event choreography using RabbitMQ! Well understood pattern, easy to extend and integrate with other systems using plain amqp
* Task retries configurable per-task, easy to write custom strategies
* Simple, less than 400 LoC
* Monitoring UI

Usage
============

```python
from inqubo.retry_strategies import LimitedRetries, no_retries
from inqubo.workflow import  Workflow
from inqubo.decorators import step

# define stome steps
@step()
async def get_data(payload, meta):
    # payload contains result of the previous step
    # meta contains meta data provided on workflow init and is static for all services
    return await fetch_some_data(meta['search_id'])


# default is 3 retries with 1 second spacing
@step(retry_strategy=LimitedRetries(number_retries=20, retry_timeout=300))
def process_data(payload, meta):
    return process_the_data(payload)


# steps can be async
@step(retry_strategy=no_retries)
async def load_data_to_external_system(payload, meta):
    await upload_it(payload)

@step()
async def load_data_to_internal_system(payload, meta):
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
    await pika_runner.trigger('test_run',
                              meta={'foo':'bar'},  # provided to every task
                              payload={'baz': 'bar'})  # send to initial task

loop.run_until_complete(main())
loop.run_forever()
```

To start rabbitmq for testing:
```bash
docker run --rm --hostname my-rabbit --name some-rabbit -p 5672:5672 -p 15672:15672 rabbitmq:3-management
```

Monitoring UI
==============
There's a separate project with a webapp that allows monitoring running workflows & triggering new ones:  
https://github.com/domasx2/inqubo-ui

Demo
==============
A demo that can be run with docker-compose, include monitoring app and sample workflows:  
https://github.com/domasx2/inqubo-demo

How it works
===============
![chart](https://raw.githubusercontent.com/domasx2/inqubo/images/inqubo.png)

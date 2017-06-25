import typing as t
import asyncio
import logging
import json
from aio_pika import connect, Message, ExchangeType, IncomingMessage, Message, Queue, Exchange

from inqubo.retry_strategies import BaseRetryStrategy
from inqubo.runners.base_runner import BaseRunner
from inqubo.runners.models import WorkflowInstance
from inqubo.workflow import Workflow, Step

logger = logging.getLogger('inqubo')


class PikaRunnerError(Exception):
    pass


class PikaClient:

    def __init__(self, ampq_url: str, event_loop: asyncio.BaseEventLoop=None):
        self.ampq_url = ampq_url
        self.event_loop = event_loop or asyncio.get_event_loop()
        self.connection = None
        self.channel = None

    async def connect(self):
        logger.info('connecting to ampq, url={}'.format(self.ampq_url))
        self.connection = await connect(self.ampq_url, loop=self.event_loop)
        self.channel = await self.connection.channel()


class PikaRunner(BaseRunner):

    def __init__(self, workflow: Workflow, pika_client: PikaClient, event_loop: asyncio.BaseEventLoop=None,
                 retry_strategy: BaseRetryStrategy=None):
        super().__init__(workflow, retry_strategy)
        self.pika_client = pika_client
        self.event_loop = event_loop or asyncio.get_event_loop()
        self.exchange = None
        self.retry_exchange = None
        self.step_queues = {}
        self.retry_queues = {}

    async def start(self):
        logger.info('starting pika runner or {}'.format(self.workflow))
        if not self.pika_client.channel:
            await self.pika_client.connect()
        self.exchange = await self.pika_client.channel.declare_exchange(self.workflow.id, type=ExchangeType.TOPIC,
                                                                        durable=True, auto_delete=False)
        self.retry_exchange = await self.pika_client.channel.declare_exchange(self.workflow.id + '_retry',
                                                                              type=ExchangeType.DIRECT,
                                                                              durable=True, auto_delete=False)
        logger.info('connected!')

        async def register_step(trigger_key: str, step: Step):
            logger.info('setting up step {} trigger key={} retry key={}'.format(step, trigger_key, step.name + '.retry'))

            def on_message(message: IncomingMessage):
                self.event_loop.create_task(self._handle_message(step, message))

            queue = await self._setup_queue(step.name, [trigger_key, step.name + '.retry'], on_message)
            self.step_queues[step.name] = queue

            for child in step.children:
                await register_step(step.name + '.success', child)

        await register_step(self.workflow.id + '.init', self.workflow.initial_step)

    async def _trigger(self, workflow_instance: WorkflowInstance, payload: t.Any):
        logger.info('triggering {}'.format(workflow_instance))
        await self._publish_message(self.workflow.id + '.init', self._build_message(workflow_instance, payload))

    async def _setup_queue(self, name: str, routing_keys: t.List[str]=[],
                           on_message: t.Callable[[IncomingMessage], None]=None,
                           exchange: Exchange=None, arguments: t.Dict[str, t.Union[str, int]]={}) -> Queue:
        logger.debug('setting up queue [{}], routing keys {}, consume={}'
                     .format(name, routing_keys, 'yes' if on_message else 'no'))
        queue = await self.pika_client.channel.declare_queue(name, durable=True, auto_delete=False, arguments=arguments)
        for key in routing_keys:
            await queue.bind(exchange or self.exchange, key)

        if on_message:
            queue.consume(on_message)
        return queue

    def _build_message(self, workflow_instance: WorkflowInstance, payload: t.Any=None) -> Message:
        return Message(
            bytes(json.dumps({'meta': workflow_instance.meta, 'payload': payload}), 'utf-8'),
            content_type='application/json',
            headers= {
                'workflow_id': self.workflow.id,
                'workflow_instance_key': workflow_instance.key
            }
        )

    async def _publish_message(self, routing_key: str, message: Message):
        logger.debug('publishing message routing_key [{}]'.format(routing_key))
        await self.exchange.publish(message, routing_key)

    async def _publish_retry(self, step: Step, message: Message, retry_attempt: int, retry_timeout: int):
        routing_key = step.name + '.retry'
        queue_name = '{}.{}'.format(routing_key, retry_timeout)
        message.headers['retry_attempt'] = retry_attempt
        if queue_name not in self.retry_queues:
            self.retry_queues[queue_name] = await self._setup_queue(name=queue_name,
                                                                    routing_keys=[queue_name],
                                                                    exchange=self.retry_exchange,
                                                                    arguments={'x-dead-letter-exchange': self.workflow.id,
                                                                               'x-message-ttl': retry_timeout,
                                                                               'x-dead-letter-routing-key': routing_key})
        logger.debug('publishing to retry queue {}'.format(queue_name))
        await self.retry_exchange.publish(message, queue_name)

    async def _handle_failure(self, step: Step, workflow_instance: WorkflowInstance,
                              exception: Exception, message: Message):
        retry_attempt = message.headers.get('retry_attempt', 0) + 1
        retry_strategy = step.retry_strategy or self.retry_strategy
        retry_after = retry_strategy.get_retry_timeout(exception, retry_attempt)
        if retry_after:
            logger.warning('{} for {} failed, queuing retry attempt {} after {}ms'
                           .format(step, workflow_instance, retry_attempt, retry_after))

            await self._publish_retry(step, message, retry_attempt, retry_after)
            payload = {
                'fatal': False,
                'attempts': retry_attempt,
                'retry_after': retry_after,
            }
        else:
            logger.error('{} for {} failed fatally after {} attempts'
                         .format(step, workflow_instance, retry_attempt))
            payload = {
                'fatal': True,
                'attempts': retry_attempt,
                'retry_after': None,
            }

        await self._publish_message(step.name + '.failure', self._build_message(workflow_instance, payload))

    async def _handle_success(self, step: Step, workflow_instance: WorkflowInstance, payload: t.Any):
        await self._publish_message(step.name + '.success', self._build_message(workflow_instance, payload))

    async def _handle_message(self, step: Step, message: IncomingMessage):
        body = json.loads(message.body)
        workflow_instance = WorkflowInstance(id=message.headers['workflow_id'],
                                             key = message.headers['workflow_instance_key'],
                                             meta = body['meta'])
        payload = body['payload']
        result = await self.execute_step(step, workflow_instance, payload)
        if result.exception:
            await self._handle_failure(step, workflow_instance, result.exception, message)
        else:
            await self._handle_success(step, workflow_instance, result.result)
        message.ack()
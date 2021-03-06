import typing as t
import asyncio
import logging
import json
from datetime import datetime
from enum import Enum
from aio_pika import connect, Message, ExchangeType, IncomingMessage, Message, Queue, Exchange, DeliveryMode

from inqubo.retry_strategies import BaseRetryStrategy
from inqubo.runners.base_runner import BaseRunner
from inqubo.runners.context import Context
from inqubo.runners.models import WorkflowInstance
from inqubo.workflow import Workflow, Step

logger = logging.getLogger('inqubo')


class Event(Enum):
    INIT = 'init'
    SUCCESS = 'success'
    FAILURE = 'failure'
    RETRY = 'retry'
    START = 'start'


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
        self.meta_exchange = None
        self.step_queues = {}
        self.retry_queues = {}

    async def start(self):
        ctx = self._ctx(WorkflowInstance(self.workflow.id, '-', None))
        ctx.log.info('starting runner')
        if not self.pika_client.channel:
            await self.pika_client.connect()
        ctx.log.info('setting up exchanges')
        self.exchange = await self.pika_client.channel.declare_exchange(self.workflow.id, type=ExchangeType.TOPIC,
                                                                        durable=True, auto_delete=False)
        self.retry_exchange = await self.pika_client.channel.declare_exchange(self.workflow.id + '_retry',
                                                                              type=ExchangeType.DIRECT,
                                                                              durable=True, auto_delete=False)
        self.meta_exchange = await self.pika_client.channel.declare_exchange('inqubo_meta',
                                                                              type=ExchangeType.DIRECT,
                                                                              durable=True, auto_delete=False)

        ctx.log.info('setting up meta')

        def on_workflow_request(message: IncomingMessage):
            with message.process():
                ctx.log.info('got workflow meta request')
                self.event_loop.create_task(self._emit_workflow_meta(ctx))

        await self._setup_queue('', ctx, ['workflow_meta_request'], on_workflow_request, self.meta_exchange)
        await self._emit_workflow_meta(ctx)

        async def register_step(trigger_key: str, step: Step):
            ctx = self._ctx(WorkflowInstance(self.workflow.id, '-', None), step)

            def on_message(message: IncomingMessage):
                self.event_loop.create_task(self._handle_message(step, message))

            queue = await self._setup_queue(step.name, ctx, [trigger_key, step.name + '.' + Event.RETRY.value], on_message)
            self.step_queues[step.name] = queue

            for child in step.children:
                await register_step(step.name + '.' + Event.SUCCESS.value, child)

        await register_step(self.workflow.id + '.' + Event.INIT.value, self.workflow.initial_step)

    async def _trigger(self, workflow_instance: WorkflowInstance, payload: t.Any):
        ctx = self._ctx(workflow_instance)
        ctx.log.info('triggering workflow!')
        await self.exchange.publish(self._build_event_message(ctx, payload), self.workflow.id + '.' + Event.INIT.value)

    async def _emit_workflow_meta(self, ctx: Context):
        ctx.log.info('emitting workflow meta')
        await self.meta_exchange.publish(self._build_message(self.workflow.serialize(), persistent=False), 'workflow_meta')

    async def _setup_queue(self, name: str, ctx: Context, routing_keys: t.List[str]=[],
                           on_message: t.Callable[[IncomingMessage], None]=None,
                           exchange: Exchange=None, arguments: t.Dict[str, t.Union[str, int]]={}) -> Queue:
        ctx.log.debug('setting up queue [{}], routing keys {}, consume={}'
                     .format(name, routing_keys, 'yes' if on_message else 'no'))
        queue = await self.pika_client.channel.declare_queue(name, durable=True, auto_delete=False, arguments=arguments)
        for key in routing_keys:
            await queue.bind(exchange or self.exchange, key)

        if on_message:
            queue.consume(on_message)
        return queue

    @staticmethod
    def _build_message(payload: t.Any={}, headers: t.Dict[str, str]={}, persistent=True) -> Message:
        return Message(
            bytes(json.dumps(payload), 'utf-8'),
            delivery_mode=DeliveryMode.PERSISTENT if persistent else DeliveryMode.NOT_PERSISTENT,
            timestamp=datetime.utcnow().timestamp(),
            content_type='application/json',
            headers=headers
        )

    def _build_event_message(self, ctx:Context, payload: t.Any=None):
        return self._build_message(
            { 'meta': ctx.workflow_instance.meta, 'payload': payload},
            { 'workflow_id': self.workflow.id, 'workflow_instance_key': ctx.workflow_instance.key }
        )
    async def _publish_event(self, ctx: Context, event: Event, payload: t.Any=None):
        message = self._build_event_message(ctx, payload)
        routing_key = '{}.{}'.format(ctx.step.name, event.value)
        ctx.log.info('publishing event [{}]'.format(routing_key))
        await self.exchange.publish(message, routing_key)

    async def _publish_retry(self, message: Message, retry_attempt: int, retry_timeout: int, ctx: Context):
        routing_key = ctx.step.name + '.' + Event.RETRY.value
        queue_name = '{}.{}'.format(routing_key, retry_timeout)
        message.headers['retry_attempt'] = retry_attempt
        if queue_name not in self.retry_queues:
            self.retry_queues[queue_name] = await self._setup_queue(name=queue_name, ctx=ctx,
                                                                    routing_keys=[queue_name],
                                                                    exchange=self.retry_exchange,
                                                                    arguments={'x-dead-letter-exchange': self.workflow.id,
                                                                               'x-message-ttl': retry_timeout,
                                                                               'x-dead-letter-routing-key': routing_key})
        ctx.log.debug('publishing to retry queue {}'.format(queue_name))
        await self.retry_exchange.publish(message, queue_name)

    async def _handle_failure(self, exception: Exception, traceback: t.Any, message: Message, ctx: Context):
        retry_attempt = message.headers.get('retry_attempt', 0) + 1
        retry_strategy = ctx.step.retry_strategy or self.retry_strategy
        retry_after = retry_strategy.get_retry_timeout(exception, retry_attempt)
        if retry_after:
            ctx.log.warning('failed, queuing retry attempt {} after {}ms'.format(retry_attempt, retry_after))

            await self._publish_retry(message, retry_attempt, retry_after, ctx)
            payload = {
                'fatal': False,
                'attempts': retry_attempt,
                'retry_after': retry_after,
            }
        else:
            ctx.log.error('failed fatally after {} attempts'.format(retry_attempt))
            payload = {
                'fatal': True,
                'attempts': retry_attempt,
                'retry_after': None,
            }
        payload['exception'] = type(exception).__name__
        payload['traceback'] = traceback


        await self._publish_event(ctx, Event.FAILURE, payload)

    async def _handle_message(self, step: Step, message: IncomingMessage):
        with message.process():
            body = json.loads(message.body)
            workflow_instance = WorkflowInstance(id=message.headers['workflow_id'],
                                                 key = message.headers['workflow_instance_key'],
                                                 meta = body['meta'])
            ctx = self._ctx(workflow_instance, step)
            payload = body['payload']
            await self._publish_event(ctx, Event.START, payload)
            result = await self.execute_step(step, workflow_instance, payload, ctx)
            if result.exception:
                await self._handle_failure(result.exception, result.traceback, message, ctx)
            else:
                await self._publish_event(ctx, Event.SUCCESS, result.result)
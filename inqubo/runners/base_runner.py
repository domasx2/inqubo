import inspect
import logging
import time
import typing as t

from inqubo.retry_strategies import BaseRetryStrategy, LimitedRetries
from inqubo.runners.models import WorkflowInstance, StepResult
from inqubo.workflow import Workflow, Step

logger = logging.getLogger('inqubo')


class BaseRunner:

    def __init__(self, workflow: Workflow, retry_strategy: BaseRetryStrategy=None):
        self.workflow = workflow
        self.retry_strategy = retry_strategy or LimitedRetries()

    async def trigger(self, key: str, meta: t.Any=None, payload: t.Any=None):
        return await self._trigger(WorkflowInstance(id=self.workflow.id, key=key, meta=meta), payload)

    async def _trigger(self, workflow_instance: WorkflowInstance, payload: t.Any):
        raise NotImplementedError

    @staticmethod
    async def execute_step(step: Step, workflow_instance: WorkflowInstance, payload: t.Any):
        logger.info('starting {} for {}'.format(step, workflow_instance))
        kwargs = {}
        args = inspect.getfullargspec(step.fn).args
        if 'workflow_instance' in args:
            kwargs['workflow_instance'] = workflow_instance
        if 'payload' in args:
            kwargs['payload'] = payload
        start = time.time()
        try:
            if inspect.iscoroutinefunction(step.fn):
                result = await step.fn(**kwargs)
            else:
                result = step.fn(**kwargs)
            logger.info('{} for {} success'.format(step, workflow_instance))
            return StepResult(duration=start - time.time(), result=result)

        except Exception as e:
            logger.error('{} for {} failed with {}'.format(step, workflow_instance, e))
            return StepResult(duration=start - time.time(), exception=e)





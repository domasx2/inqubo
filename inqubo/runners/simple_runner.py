import asyncio
import logging
import typing as t

from inqubo.retry_strategies import BaseRetryStrategy
from inqubo.runners.base_runner import BaseRunner
from inqubo.runners.models import WorkflowInstance
from inqubo.workflow import Workflow, Step

logger = logging.getLogger('inqubo')


class SimpleRunFailure(Exception):

    def __init__(self, errors: t.Dict[str, Exception]={}):
        self.errors = errors


class SimpleRunner(BaseRunner):

    def __init__(self, workflow: Workflow, event_loop: asyncio.BaseEventLoop=None,
                 retry_strategy: BaseRetryStrategy=None):
        super().__init__(workflow, retry_strategy)
        self.event_loop = event_loop or asyncio.get_event_loop()

    def _trigger(self, workflow_instance: WorkflowInstance, payload: t.Any=None) -> asyncio.Future:
        logger.info('triggering execution of {}'.format(workflow_instance))
        pending: t.Dict[str, str]={}
        trigger_fut = asyncio.Future()

        errors: t.Dict[str, Exception] = {}

        def run_step(step: Step, step_payload: t.Any, attempt_no:int = 0):
            if attempt_no:
                logger.info('retry attempt {} for {} {}'.format(attempt_no, step, workflow_instance))
            pending[step.name] = 'running'
            step_future = self.event_loop.create_task(self.execute_step(step, workflow_instance, step_payload))

            def callback(step_future: asyncio.Future):
                del pending[step.name]
                result = step_future.result()
                if result.exception:
                    retry_strategy = step.retry_strategy or self.retry_strategy
                    retry_after = retry_strategy.get_retry_timeout(result.exception, attempt_no + 1)
                    if retry_after:
                        logger.error('{} failed, retrying after {} ms'.format(step, retry_after))
                        pending[step.name] = 'pending retry'

                        def retry(retry_future):
                            run_step(step, payload, attempt_no + 1)

                        retry_future = self.event_loop.create_task(asyncio.sleep(retry_after / 1000))
                        retry_future.add_done_callback(retry)
                    else:
                        logger.error('{} failed after {} attempts, not continuing this branch'.format(step, attempt_no))
                        errors[step.name] = result.exception
                else:
                    for child in step.children:
                        run_step(child, result.result)
                if not pending:
                    logger.info('execution of {} ended'.format(workflow_instance))
                    if errors:
                        trigger_fut.set_exception(SimpleRunFailure(errors))
                    else:
                        trigger_fut.set_result(None)

            step_future.add_done_callback(callback)

        run_step(self.workflow.initial_step, payload)
        return trigger_fut



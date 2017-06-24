import typing as t
import logging
import asyncio
from inqubo.runners.base_runner import BaseRunner
from inqubo.models import WorkflowInstance
from inqubo.workflow import  Workflow, Step

logger = logging.getLogger('inqubo')


class SimpleRunner(BaseRunner):

    def __init__(self, workflow: Workflow, event_loop: asyncio.BaseEventLoop):
        super().__init__(workflow)
        self.event_loop = event_loop or asyncio.get_event_loop()

    def _trigger(self, workflow_instance: WorkflowInstance, payload: t.Any=None) -> asyncio.Future:
        logger.info('triggering execution of {}'.format(workflow_instance))
        pending: t.Dict[str, str]={}
        trigger_fut = asyncio.Future()

        def run_step(step: Step, step_payload: t.Any):
            pending[step.name] = 'running'
            step_future = self.event_loop.create_task(self.execute_step(step, workflow_instance, step_payload))

            def callback(step_future: asyncio.Future):
                del pending[step.name]
                result = step_future.result()
                if result.exception:
                    logger.error('{} failed, not continuing this branch'.format(step))
                else:
                    for child in step.children:
                        run_step(child, result.result)
                if not pending:
                    logger.info('execution of {} ended'.format(trigger_fut))
                    trigger_fut.set_result(None)

            step_future.add_done_callback(callback)

        run_step(self.workflow.initial_step, payload)
        return trigger_fut



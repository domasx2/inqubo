import logging

from inqubo.runners.models import WorkflowInstance
from inqubo.workflow import Step

logger = logging.getLogger('inqubo.handler')


class LoggerAdapter(logging.LoggerAdapter):

    def process(self, msg, kwargs):
        return '[{}][{}][{}] {}'.format(self.extra['workflow_id'],
                                    self.extra['workflow_key'],
                                    self.extra['step_name'], msg), kwargs


class Context:

    def __init__(self, workflow_instance: WorkflowInstance=None, step: Step=None):
        self.workflow_instance = workflow_instance
        self.step = step
        self.log = LoggerAdapter(logger, {
            'workflow_id':  workflow_instance.id if workflow_instance else '-',
            'workflow_key': workflow_instance.key if workflow_instance else '-',
            'step_name': step.name if step else '-'
        })

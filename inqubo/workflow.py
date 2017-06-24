import typing as t
from inqubo.typing import StepCallable

StepOrFn = t.Union['Step', StepCallable]

class Workflow:

    def __init__(self, id: str):
        self.id = id
        self._initial_step: Step = None

    def start(self, step: StepOrFn) -> 'Step':
        self._initial_step = Step._make(step)
        return self._initial_step

    def serialize(self) -> t.Dict[str, t.Any]:
        return {
            'workflow_id': self.id,
            'initial_step': self._initial_step.serialize() if self._initial_step else None
        }


class Step:

    def __init__(self, fn: StepCallable, name: str=None, parent: 'Step'=None):
        self.name = name or fn.__name__
        self.fn = fn
        self.parent = parent
        self.children: t.List[Step] = []

    def then(self, *steps: t.List[StepOrFn]) -> t.Union[None, 'Step']:
        for step in steps:
            step = self._make(step)
            step.parent = self
            self.children.append(step)
        if len(steps) == 1:
            return self.children[0]
        return None

    def __str__(self):
        return self.name

    def serialize(self) -> t.Dict[str, t.Any]:
        return {
            'name': self.name,
            'children': [c.serialize() for c in self.children]
        }


    @classmethod
    def _make(cls, step: StepOrFn):
        if isinstance(step, Step):
            return step
        elif isinstance(step, t.Callable):
            if hasattr(step, '_step'):
                return step._step
            raise TypeError('step function {} should be annotated with @step()'.format(step.__name__))
        else:
            raise TypeError('expected instance of Step or function annotated with @step, got {}'.format(step))




import typing as t


class WorkflowInstance(t.NamedTuple):
    id: str
    key: str
    meta: t.Dict[str, t.Any]=None

    def __str__(self):
        return 'workflow [{}] instance [{}]'.format(self.id, self.key)


class StepResult(t.NamedTuple):
    duration: int
    result: t.Any=None
    exception: Exception=None
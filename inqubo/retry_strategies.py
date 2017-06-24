class BaseRetryStrategy:

    def get_retry_timeout(self, error: Exception, retry_attempt: int) -> int:
        # return number of milliseconds to retry after. If falsy, not retried at all
        raise NotImplementedError


class LimitedRetries(BaseRetryStrategy):

    def __init__(self, number_retries: int=3, retry_timeout: int=1000):
        self.number_retries = number_retries
        self.retry_timeout = retry_timeout

    def get_retry_timeout(self, error: Exception, retry_attempt: int):
        if retry_attempt <= self.number_retries:
            return self.retry_timeout


no_retries = LimitedRetries(number_retries=0)
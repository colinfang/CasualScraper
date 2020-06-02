import logging

LOGGER = logging.getLogger(__name__)


def retry(f, num_tries: int):
    for i in range(num_tries):
        try:
            return f()
        except Exception as e:
            if i < num_tries - 1:
                LOGGER.warning(f'{e!r} -> Retrying {i} time')
                continue
            else:
                raise

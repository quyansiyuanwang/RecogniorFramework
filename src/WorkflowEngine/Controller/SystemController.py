import time
from typing import List

from ...WorkflowEngine.Controller.LogController import LogLevel
from .Runner import SafeRunner


class SystemController:
    @staticmethod
    def sleep(
        ms: float,
        debug: bool = True,
        ignore: bool = False,
        prefix: str = "",
        levels: List[LogLevel] = [LogLevel.DEBUG],
    ) -> None:
        if ms <= 0:
            if ignore or ms == 0:
                return
            raise ValueError("Sleep duration must be non-negative")

        SafeRunner.run(
            time.sleep,
            (ms / 1000,),
            debug=debug,
            ignore=ignore,
            # logger
            context={"ms": ms},
            debug_msg=f"{prefix} Sleeping for {ms} ms",
            warn_msg=f"{prefix} Failed to sleep for {ms} ms",
            err_msg=f"{prefix} Error sleeping for {ms} ms: {{error}}",
            log_lvl=levels,
        )

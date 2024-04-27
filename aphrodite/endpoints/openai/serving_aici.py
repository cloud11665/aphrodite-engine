from typing import List, Optional

from fastapi import Request
from pyaici.comms import AiciRunner

from aphrodite.engine.async_aphrodite import AsyncLLMEngine
from aphrodite.endpoints.openai.serving_engine import OpenAIServing
from aphrodite.common.utils import random_uuid

from .protocol import RunRequest


class AiciRunnerCompletion(OpenAIServing):

    def __init__(self, aici_runner: AiciRunner, engine: AsyncLLMEngine,
                 served_model: str):
        super().__init__(engine=engine, served_model=served_model)
        self.aici_runner = aici_runner
        self.empty_prompt: List[int] = self.tokenizer("").input_ids
        # TODO: this is a hack:
        engine.engine.scheduler.aici_runner = aici_runner

    # this is separate from create_completion() so fastapi exceptions
    # from .instantiate_async() are properly sent to the user
    async def prep_completion(self, request: RunRequest):
        request_id = f"run-{random_uuid()}"
        prompt = request.prompt
        inst_res = await self.aici_runner.instantiate_async(
            request_id, prompt, request.controller, request.controller_arg)
        return request_id, inst_res

    async def create_completion(self, request_id: str, inst_res: Optional[dict],
                                request: RunRequest, raw_request: Request):
        """Completion API for AICI controllers.
        See https://github.com/microsoft/aici/blob/main/docs/REST.md
        """
        runner = self.aici_runner
        prompt = request.prompt
        yield runner.data_line(
            runner.initial_json(request_id, self.served_model))

        if inst_res is not None:
            # error case
            yield runner.data_line(inst_res)
            yield runner.final_data()
            return

        sampling_params = request.to_sampling_params()
        generator = self.engine.generate(prompt, sampling_params, request_id)

        previous_texts = []
        ff_tokens = len(prompt)
        sampled_tokens = 0

        async for res in generator:
            # Abort the request if the client disconnects.
            if await raw_request.is_disconnected():
                await self.engine.abort(request_id)
                raise StopAsyncIteration()
            forks = []
            for output in res.outputs:
                # TODO:
                ff_tokens += 1
                sampled_tokens += 1

                i = output.index
                while len(previous_texts) <= i:
                    previous_texts.append("")
                delta_text = output.text[len(previous_texts[i]):]
                previous_texts[i] = output.text

                fork_res = runner.seq_logs(
                    output.seq_id,
                    index=i,
                    text=delta_text,
                    finish_reason=output.finish_reason,
                )
                forks.append(fork_res)
            yield runner.data_line(
                runner.run_json(forks,
                                runner.usage_json(ff_tokens, sampled_tokens)))

        yield runner.final_data()

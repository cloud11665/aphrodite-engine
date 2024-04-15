"""Test the different finish_reason="stop" situations during generation:
    1. One of the provided stop strings
    2. One of the provided stop tokens
    3. The EOS token

Run `pytest tests/engine/test_stop_reason.py`.
"""

import pytest
import transformers

from aphrodite import SamplingParams

MODEL = "facebook/opt-350m"
STOP_STR = "."
SEED = 42
MAX_TOKENS = 1024


@pytest.fixture
def aphrodite_model(aphrodite_runner):
    aphrodite_model = aphrodite_runner(MODEL)
    yield aphrodite_model
    del aphrodite_model


def test_stop_reason(aphrodite_model, example_prompts):
    tokenizer = transformers.AutoTokenizer.from_pretrained(MODEL)
    stop_token_id = tokenizer.convert_tokens_to_ids(STOP_STR)
    llm = aphrodite_model.model

    # test stop token
    outputs = llm.generate(example_prompts,
                           sampling_params=SamplingParams(
                               seed=SEED,
                               max_tokens=MAX_TOKENS,
                               stop_token_ids=[stop_token_id]))
    for output in outputs:
        output = output.outputs[0]
        assert output.finish_reason == "stop"
        assert output.stop_reason == stop_token_id

    # test stop string
    outputs = llm.generate(example_prompts,
                           sampling_params=SamplingParams(
                               seed=SEED, max_tokens=MAX_TOKENS, stop="."))
    for output in outputs:
        output = output.outputs[0]
        assert output.finish_reason == "stop"
        assert output.stop_reason == STOP_STR

    # test EOS token
    outputs = llm.generate(example_prompts,
                           sampling_params=SamplingParams(
                               seed=SEED, max_tokens=MAX_TOKENS))
    for output in outputs:
        output = output.outputs[0]
        assert output.finish_reason == "length" or (
            output.finish_reason == "stop" and output.stop_reason is None)

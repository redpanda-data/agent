import os

import pytest
from pydantic import BaseModel

from redpanda import agents


class MyModel(BaseModel):
    color: str


@pytest.mark.skipif(
    "OPENAI_API_KEY" not in os.environ, reason="Yo dog someone has to pay for those tokens"
)
@pytest.mark.asyncio
async def test_llm_prompt():
    my_agent = agents.Agent(
        name="GPT Agent",
        model="openai/gpt-4o",
        response_type=MyModel,
        max_tokens=10,
    )
    resp = await my_agent.run(input="In one word what color is the sky?")
    assert resp.color in ["blue", "azure"], f"expected color to be blue or azure, got: {resp.color}"

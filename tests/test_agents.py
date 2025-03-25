import pytest

import agents


@pytest.mark.asyncio
async def test_hello():
    assert agents.hello() == "Hello from agent!"

# Redpanda Agents

The [Redpanda Agent SDK](https://github.com/redpanda-data/agent) allows you to build agentic [Redpanda Connect](https://www.redpanda.com/connect) pipelines.

You can use [`rpk`](https://docs.redpanda.com/current/get-started/intro-to-rpk/) to generate the initial boilerplate for an agentic pipeline.

```bash
$ rpk connect agent init my_first_agent

$ ls --tree ./my_first_agent
my_first_agent
├── agents
│   └── weather.py
├── mcp
│   └── resources
│       └── processors
│           └── check_weather_tool.yaml
├── pyproject.toml
├── README.md
├── redpanda_agents.yaml
└── uv.lock
```

## Project Structure

The project structure is as follows:

### `redpanda_agents.yaml`

The main entry point for the agent pipeline. The file looks like the following:

```yaml
# Each agent is an entry under `agents` - there can be multiple for multi-agent flows.
agents:
  # The name of the agent determines what python file is executed for the agent.
  <agent_name>:
    # Any Redpanda Connect input is valid here
    # See them all at: https://docs.redpanda.com/redpanda-connect/components/inputs/about/
    input:
      <input>
    # Any tool labels defined in the `mcp` directory, see notes below for more.
    tools:
      - <tool label>
    # Any Redpanda Connect output is valid here
    # See them all at https://docs.redpanda.com/redpanda-connect/components/outputs/about/
    output:
      <output>
    # Configure Redpanda Connect to send tracing events to Jaeger, Open Telemetry collector and more.
    # See options here: https://docs.redpanda.com/redpanda-connect/components/tracers/about/
    tracer:
        <tracer>
```

### `agents/*.py`

Each agent receives input from `input` and sends its output to `output`. You can create an agent
by importing from `redpanda.agents`. Creating an `Agent` looks like:

```python
my_agent = Agent(
    name="my_first_agent",
    model="openai/gpt-4o",
    instructions="These are your instructions - good luck!",
)
```

In this example, OpenAI GPT-4o is configured and requires you to set `OPENAI_API_KEY` as an environment variable.

Once you've created the agent, you pass it off to the runtime to handle messages in the pipeline like so:

```python
asyncio.run(redpanda.runtime.serve(my_agent))
```

### `mcp/resources/processors/*.yaml`

In order to give tools to your agent, you need to first define them as yaml files with the following structure:

```yaml
label: '<label>'
processors:
  - <processors>
meta:
  mcp:
    enabled: true
    description: '<description>'
```

The `<label>` is what must be provided under the list of `tools` in the agent YAML file, while the
processors can be any [Redpanda Connect processor](https://docs.redpanda.com/redpanda-connect/components/processors/about/).

<!--
TODO

### `mcp/resources/caches/*.yaml`

### `mcp/o11y/tracer.yaml`

### `mcp/o11y/metrics.yaml`

-->

## Running

To run our agent, we can do that with `rpk connect agent run my_first_agent`


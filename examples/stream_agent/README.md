# Redpanda Agent

This is an example agent that showcases how you can leverage a message broker as a an input/output for an agent (as well as any of Redpanda Connect's other input or output components).

You can run this agent via:

```
rpk container start
rpk topic create agent_input agent_output
rpk connect agent run .
```

Then you can give input to the agent using `rpk topic produce agent_input`, and see the agent's output via `rpk topic consume agent_output`. Using Redpanda as a message broker allows you to replay, resume messages in multi-agent systems.

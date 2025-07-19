## Observability demo

This demo shows how to view open telemetry traces within your pipelines.

First generate an OPENAI API Key and set as an environment variable: https://platform.openai.com/docs/api-reference/introduction

```
export OPENAI_API_KEY= <API KEY>

```

Next start a local [jaeger] instance like this:

```
docker run --rm --name jaeger \
  -p 16686:16686 \
  -p 4317:4317 \
  -p 4318:4318 \
  -p 5778:5778 \
  -p 9411:9411 \
  jaegertracing/jaeger:2.5.0
```

Then run the agent like so:

```
rpk connect agent run .
```

After asking a question like `What is the weather in Chicago?` and pressing enter,
you should be able to see traces shortly in the jaeger UI at localhost:16686

[jaeger]: https://www.jaegertracing.io/


import traceback
import uuid

from crewai import Agent, Crew, Process, Task
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

load_dotenv()

app = FastAPI()

@app.get("/health")
def health():
    return {"ok": True}


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[dict]  # [{"role":"user","content":"hello"}]
    temperature: float | None = None
    stream: bool | None = False


def run_crewai(user_text: str) -> str:
    # Minimal CrewAI example: 1 agent, 1 task
    agent = Agent(
        role="Assistant",
        goal="Reply helpfully and concisely.",
        backstory="You are a helpful AI agent hosted for ADP integration.",
        verbose=True,
        allow_delegation=False,
    )

    task = Task(
        description=f"User said: {user_text}\nReply to the user.",
        expected_output="A helpful natural-language reply to the user.",
        agent=agent,
    )

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=1,
    )

    result = crew.kickoff()
    return str(result)


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    try:
        user_text = ""
        for m in reversed(req.messages):
            if m.get("role") == "user":
                user_text = (m.get("content") or "").strip()
                break

        if not user_text:
            return {
                "error": {
                    "message": "No user message provided.",
                    "type": "invalid_request_error",
                }
            }

        answer = run_crewai(user_text)

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
        }
    except Exception:
        traceback.print_exc()
        return {
            "error": {
                "message": "An internal error occurred.",
                "type": "internal_error",
            }
        }

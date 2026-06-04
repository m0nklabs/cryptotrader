import os
import sys
import json
import subprocess
import time
from openai import OpenAI, RateLimitError, APIError


def run_gh_command(command):
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running gh command: {command}", file=sys.stderr)
        return None
    return result.stdout.strip()


def get_issue_context(issue_number, repo):
    # Fetch issue title, body, and comments
    cmd = f"gh issue view {issue_number} --repo {repo} --json title,body,comments"
    data = run_gh_command(cmd)
    if not data:
        return None
    return json.loads(data)


def call_llm_with_retry(client, model, messages, max_retries=5):
    """Calls LLM with exponential backoff for Rate Limits (429)."""
    base_delay = 2

    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise e

            delay = base_delay * (2**attempt)
            print(f"Rate limit hit (429). Retrying in {delay}s... (Attempt {attempt + 1}/{max_retries})")
            time.sleep(delay)
        except APIError as e:
            # Handle 502/503 errors from OpenRouter/Proxy
            if e.status_code in [502, 503, 504]:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2**attempt)
                print(f"API Error ({e.status_code}). Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise e

    return None


def main():
    # Configuration from Environment
    api_key = os.environ.get("LLM_API_KEY")
    # Support for custom proxy URL (e.g. http://localhost:8080/v1 or https://my-proxy.com/v1)
    base_url = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.environ.get("LLM_MODEL", "anthropic/claude-3.5-sonnet")

    repo = os.environ.get("GITHUB_REPOSITORY")
    issue_number = os.environ.get("ISSUE_NUMBER")
    comment_body = os.environ.get("COMMENT_BODY", "")

    if not api_key:
        print("Error: LLM_API_KEY not set")
        sys.exit(1)

    print(f"Initializing Client with Base URL: {base_url}")

    # Initialize Client (OpenAI compatible)
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    # Get Context
    context = get_issue_context(issue_number, repo)
    if not context:
        print("Failed to fetch issue context")
        sys.exit(1)

    # Construct System Prompt
    system_prompt = """You are an expert AI software engineer assisting with a GitHub repository.
    You have access to the issue details and conversation history.
    Your goal is to provide high-quality, actionable technical advice, code snippets, or architectural plans.

    When asked for code, provide production-ready code.
    When asked for a plan, provide a step-by-step breakdown.
    """

    # Construct User Message
    # Combine issue description + history + current request
    issue_str = f"Title: {context['title']}\n\nDescription:\n{context['body']}\n\n"

    # Add recent comments for context (limit to last 5 to save tokens)
    comments = context.get("comments", [])[-5:]
    history_str = "\n".join([f"User {c['author']['login']}: {c['body']}" for c in comments])

    full_prompt = f"Context (Issue #{issue_number}):\n{issue_str}\n\nRecent Discussion:\n{history_str}\n\nUser Request:\n{comment_body}"

    print(f"Calling LLM ({model})...")

    try:
        response = call_llm_with_retry(
            client=client,
            model=model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": full_prompt}],
        )

        answer = response.choices[0].message.content

        # Output the answer to a file so the workflow can read it
        with open("agent_response.md", "w") as f:
            f.write(f"### 🤖 Custom Agent ({model})\n\n")
            f.write(answer)

    except Exception as e:
        print(f"Error calling LLM: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

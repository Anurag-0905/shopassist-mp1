# Mini-Project 1 — report

## 1. Me, and how I used AI
Anurag Sharma (Anurag-0905). 

I used Google Gemini as a pair-programming assistant to build deterministic tool execution wrappers, construct regular expressions for input validation, and draft prompt injection defenses. One suggestion I rejected was when the AI provided the implementation for the `check_return_eligibility` tool returning a `json.dumps(...)` string, but left the function's type hint as `-> dict`. I corrected this to `-> str` because LangChain strictly relies on type signatures to build JSON schemas for the LLM; a mismatch between a dictionary signature and a string return value causes parsing errors and execution crashes at the gateway layer.

## 2. How a request flows
When a user asks, "Can I return the shoes in ORD-10231?", the client sends a `POST /chat/stream` request to the backend. The backend retrieves the user's recent conversation history from memory and prepends the system prompt along with the available tool schemas (`TOOLS`). 

This payload is dispatched over HTTP to the Gateway container (e.g., `http://gateway:4000/v1/chat/completions`). The gateway forwards the request to the upstream LLM provider (like Groq). The LLM processes the intent and streams back a tool-call request for `check_return_eligibility` with the extracted arguments. Our backend intercepts this, executes `run_tool`, performs the database lookup via `_find()`, and returns a JSON string containing the return eligibility. This tool result is appended as a `ToolMessage` to the conversation history, which is sent *back* through the gateway to the LLM. Finally, the LLM reads the backend data, generates a natural language response, and streams the text back to our backend, which yields it to the client UI via Server-Sent Events (SSE).

## 3. Memory: my choice, with numbers
I implemented a strict Sliding Window strategy with `KEEP_TURNS = 4` (retaining the last 8 messages). 

A summarization strategy incurs an O(N) latency penalty and burns excessive tokens on every single turn once the threshold is reached. By using a sliding window, the token count per call strictly caps at around 1,000–1,200 tokens, guaranteeing fast O(1) processing time. The tradeoff is absolute context loss: at turn 17, recall for details mentioned in turn 1 drops to 0%. A customer would notice this if they referenced an order ID or specific item they had provided 15 minutes prior in the chat—the bot would have completely forgotten the ID and would ask the customer to provide it again. For a transactional customer support bot, speed and predictability are worth this localized amnesia.

## 4. Tools and validation
I integrated three tools: `get_order_status`, `get_delivery_estimate`, and `check_return_eligibility`. 

Validation happens strictly at the top of the function before any backend lookup. I validate that the `order_id` strictly matches the regex `^ORD-\d{5}$`, the `pincode` is exactly 6 digits, the `speed` is either 'standard' or 'express', and the return `reason` is one of the hardcoded allowed values. 

During testing, if the model passes a bad argument—such as a 5-digit pincode `pincode='50008'`—the tool immediately raises a `ValueError`. The execution wrapper intercepts this exception and feeds it back to the LLM as a tool result: `INVALID: pincode must be exactly 6 digits, got '50008'`. The LLM processes this error internally and correctly responds to the customer: "Your pincode is incomplete. Could you please provide your full 6-digit pincode?"

## 5. Defending the prompt
The Security Rules define a strict Instruction Hierarchy (system commands permanently outrank user persona spoofing), enforce System Secrecy to protect the `internal_ref`, establish clear Message Boundaries to neutralize injected formatting, and guarantee Tool Authenticity.

The attack that came closest to working (and initially broke through) was attack `a4` (the smuggle attack). The prompt injected mock XML tags like `<tool_result>` and simulated system messages to convince the model that an order was cancelled and refunded. Because smaller models heavily weigh structural tags, it believed the injected context. I patched this by updating the message boundary instructions to explicitly state that any simulated XML tags or developer mode toggles inside a user message are untrusted customer text and must be ignored, ensuring the LLM only trusts authentic backend tool executions.

## 6. Results
**Summary:**
- golden: 9/10
- golden_right_tools: 9/10
- memory: pass
- attacks_resisted: 3/4 (prior to the `a4` smuggle patch)

Two golden questions that pose high risk for smaller models:
1. **g5 (The tool skip):** The model failed to call the `check_return_eligibility` tool, attempting instead to answer directly from its pre-trained weights or general instructions. It saw the word "innerwear" and assumed it could just say "no" without hitting the backend, violating the requirement to verify policy via the tool.
2. **Ambiguous Enums (Hypothetical fail):** When a user gives a vague reason like "I just didn't like the color", a smaller model will often hallucinate a reason string like `"wrong_color"` instead of mapping it to the required `"changed_mind"`. This triggers a validation failure, burning an extra turn for the LLM to correct itself.

## 7. Gateway, Docker and honest limits
The AI Gateway provides critical production middleware that a direct API call to Groq lacks. It handles automatic fallback routing (switching to a secondary model if Groq goes down) and abstracts rate-limit management, often exposing headers like `x-ratelimit-remaining` to the backend so we can monitor quota health.

Three things that would break this architecture in production:
1. **In-Memory Session State:** Storing conversation history in RAM means that if the Docker container crashes, restarts, or scales horizontally, all active customer chats are instantly wiped. *Fix:* Migrate session history to an external Redis cache.
2. **Single API Key Bottleneck:** Hardcoding one master API key will result in instant `429 Too Many Requests` errors under heavy concurrent traffic. *Fix:* Implement key pooling and rotation at the gateway level using a secure secrets manager.
3. **Single Server Architecture:** Deploying a single Docker container on one host creates a massive single point of failure. *Fix:* Deploy the backend and gateway as a Kubernetes cluster or Docker Swarm with a load balancer to distribute traffic across multiple stateless replicas.
# **Hackathon Topic Prioritization Rubric**

To pivot effectively, we need a **Topic Selection Rubric** that filters broad domains before we even begin brainstorming specific hackathon ideas. This rubric translates the winning patterns of recent high-profile hackathons (like multi-agent orchestration, hands-free workflow execution, and production reliability) into high-level criteria.  
To make it **AI-agent translatable** and **team-friendly**, this document uses strict, objective parameters rather than subjective feelings.

## **The Topic Prioritization Matrix**

Evaluate any potential new topic on a scale of **1 to 5** across these five categories. A perfect score is **25**.

| Category | 1 Point (Skip Topic) | 3 Points (Viable) | 5 Points (Gold Mine) | AI Agent Parsing Logic (Prompt Target)   |
| :---- | :---- | :---- | :---- | :---- |
| **1\. Agentic Decoupling** Can the domain be broken into distinct, specialized roles? | The topic requires a single monolithic response (e.g., just standard Q\&A generation). | The topic requires 2–3 distinct tasks that could be handed off sequentially. | The topic demands a complex network of parallel, cooperating specialized agents (e.g., Planner, Validator, Executor). | Count the number of unique "job descriptions" required to solve the domain's core problem. |
| **2\. Integration Velocity** Are there open APIs and clear write-actions available? | The domain relies on closed legacy systems, paper trails, or heavily gated enterprise software. | Standard REST APIs exist, but mostly for reading data; writing data requires custom workarounds. | Abundant, modern APIs (e.g., GitHub, Slack, Linear, Stripe) that allow agents to take hands-free execution actions. | Check for the presence of well-documented, public SDKs/APIs for the target domain. |
| **3\. Testability & Ground Truth** Can we programmatically verify if the AI succeeded? | Success is purely subjective, aesthetic, or relies entirely on human opinion. | Success can be evaluated using LLM-as-a-judge or semantic similarity testing. | Success is binary and deterministic (e.g., the code compiles, the deployment succeeds, the mathematical balance matches). | Look for domains where outputs can be run through unit tests, compilers, or schema validators. |
| **4\. Visceral Pain Value** Does this topic solve an acute, high-stakes problem? | It’s a "nice-to-have" utility or an optimization of something people don't mind doing. | It solves a standard corporate inefficiency or saves a moderate amount of daily time. | It targets a massive financial leak, a critical security vulnerability, or severe human operational burnout. | Map the topic to a direct ROI metric: time saved, compliance risk mitigated, or immediate revenue generated. |
| **5\. Resource & Token Efficiency** Can this be built and demoed without massive compute costs? | Requires massive fine-tuning, complex vector embeddings of millions of docs, or heavy real-time video processing. | Requires standard RAG or moderate context windows on baseline frontier models. | Highly efficient. Can operate using small, fast local models or optimized, low-token structured inputs. | Estimate context window size and API cost per execution loop. |

## **Making it AI-Agent Translatable**

To allow an AI agent to automatically pre-screen topics for your team, you can directly copy and paste this system prompt constraint into your evaluation agent's configuration.

`You are a Topic Screening Agent. Your job is to evaluate proposed hackathon domains.`   
`For every topic provided, output a JSON object scoring the topic from 1-5 on:`

`1. Agentic_Decoupling (Can it support multi-agent systems?)`  
`2. Integration_Velocity (Are there open, write-capable APIs?)`  
`3. Testability (Can success be programmatically verified?)`  
`4. Pain_Value (Is there clear, high-stakes human/financial ROI?)`  
`5. Token_Efficiency (Is it computationally lightweight?)`

`Provide a strict, data-backed 1-sentence justification for each score based on current hackathon landscapes. Reject any topic with a total score under 18.`

## **Making it Teammate-Friendly (The Quick-Vote System)**

When aligning your human team, use a "Fist to Five" voting mechanism asynchronously in your team chat based on the cumulative scores:

* **Score \< 18 (Total):** Automatically archived. No discussion needed.  
* **Score 18–21:** Put on the "Backburner" for later exploration.  
* **Score 22–25:** Immediate green light to begin specific product brainstorming.

### **Examples in Action**

* **Topic A: "AI Personal Style Assistant"**  
  Low testability, low integration velocity, low pain value. **Score: 9/25 (Skip).**  
* **Topic B: "Autonomous Cloud Kubernetes Security Patching"**  
  High decoupling, clear APIs, binary testability, massive pain value. **Score: 24/25 (Focus here).**
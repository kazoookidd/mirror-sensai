# Sensai: documentation

Installation, configuration, commands and how each feature works are in the
[README at the root of the project](../README.md): it is the only reference, kept
up to date with the code.

This folder holds what the README does not:

| File | Content |
|---|---|
| [Scenario.md](Scenario.md) | The use case: who uses Sensai, for what, and why it runs locally |
| [user_stories/](user_stories/) | The user stories and acceptance criteria of each feature |
| [benchmarks/chat_models.md](benchmarks/chat_models.md) | Chat models compared on Sensai's own scenarios, on this machine |
| [benchmarks/embedding_models.md](benchmarks/embedding_models.md) | Embedding models compared for the RAG and the semantic cache |
| [benchmarks/rag_reranking.md](benchmarks/rag_reranking.md) | Reranking of the RAG excerpts compared (R2) |
| [images/](images/) | Screenshots of the web interface, shown in the README and the user stories |

## Features and their user stories

| Code | Feature | User stories |
|---|---|---|
| B1 | CLI chatbot: streaming, history, error handling | [B1_M1_M2_memory.md](user_stories/B1_M1_M2_memory.md) |
| M1 | Accounts, persistent history, several conversations, user profile | [B1_M1_M2_memory.md](user_stories/B1_M1_M2_memory.md) |
| M2 | Context compression, token limit and usage | [B1_M1_M2_memory.md](user_stories/B1_M1_M2_memory.md), [M2_token_limit.md](user_stories/M2_token_limit.md) |
| R1 | RAG over the HR documents, files joined to a chat | [R1_rag.md](user_stories/R1_rag.md) |
| R2 | Advanced RAG: reranking, score per excerpt, filter by document | [R2_rag_advanced.md](user_stories/R2_rag_advanced.md) |
| A1 | ReAct agent and its reasoning trace | [A1_react.md](user_stories/A1_react.md) |
| T3 | Web search, with personal details removed | [T3_web_search.md](user_stories/T3_web_search.md) |
| EV2 | Content & privacy guardrails on the chat | [EV2_guardrails.md](user_stories/EV2_guardrails.md) |
| A3 | Human in the loop: leave requests confirmed by the user | [A3_human_in_the_loop.md](user_stories/A3_human_in_the_loop.md) |
| A5 | Personas, model switching at runtime | [A5_personas.md](user_stories/A5_personas.md) |
| A6 | Semantic cache | [A6_cache.md](user_stories/A6_cache.md) |
| X1 | Web interface | [X1_web_ui.md](user_stories/X1_web_ui.md) |
| X2 | Branches and stopping an answer | [X2_branches_stop.md](user_stories/X2_branches_stop.md) |
| X3 | Export and public link | [X3_export_share.md](user_stories/X3_export_share.md) |
| | Temperature, seed, answer length | [parameters_temperature.md](user_stories/parameters_temperature.md), [parameters_seed_num_predict.md](user_stories/parameters_seed_num_predict.md) |

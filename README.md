# Reviewer Academic Text - Multi-Agent Academic Review System

## Overview
**Reviewer Academic Text** is a research-backed, state-of-the-art computational framework built on **Artificial Intelligence and Multi-Agent Systems (MAS)**. Designed to revolutionize the peer-review process of academic manuscripts—such as theses, dissertations, and scientific papers—this repository provides a robust, autonomous solution for identifying complex normative infractions (e.g., ABNT/APA compliance) and deep semantic inconsistencies (e.g., logical flaws, insufficient methodological rigor).

Unlike traditional grammar checkers, this system operates at the macro-level of academic writing. It stands out through its unique architectural qualities:
* **Cost-Efficiency by Design:** Dynamically allocates LLMs (from lightweight models to premium frontier models) based on the specific complexity of each text section, optimizing API costs without sacrificing quality.
* **Autonomous Self-Improvement:** Utilizes a Retrieval-Augmented Generation (RAG) episodic memory to continuously learn from past review successes and failures.
* **Deterministic Quality Control:** Employs an LLM-as-a-Judge feedback loop to rigorously score, filter, and reject hallucinated or superficial critiques before they reach the user.
* **Advanced Collaborative Topologies:** Capable of orchestrating complex agent behaviors, including multi-agent debates, sequential refinement chains, and specialist consensus (Ensemble/Star).

By automating the heavy lifting of structural and semantic reviews, this tool significantly reduces the cognitive load on academic advisors and examination boards, allowing them to focus on the intellectual and scientific core of the research.

## The Multi-Agent Workflow
The system's orchestration is governed by **LangGraph** in an iterative, dynamic, and concurrent 8-step workflow. Instead of relying on a single monolithic prompt, the system breaks down the review process into specialized agents and dynamic topologies.

### 1. Ingestion and Parsing
The system ingests raw PDF files using GPU-accelerated OCR models (*MinerU*, *Docling*, or *MarkItDown*). It preserves the document's structural hierarchy and automatically segments the text into canonical academic sections (e.g., Introduction, Methodology, Results). Each section is processed **concurrently** from this point forward.

### 2. Episodic Memory and Retrieval (RAG)
For each section, the system generates mathematical embeddings and queries a local **ChromaDB** vector database. It retrieves the historical context of past reviews for similar sections, fetching data on which multi-agent architectures succeeded or failed, their evaluation scores, and their computational costs.

### 3. Dynamic Routing (Router Agent)
Powered by *In-Context Learning*, the **Router Agent** analyzes the current section alongside the retrieved RAG history. It acts as a meta-decision maker, autonomously selecting the ideal multi-agent topology for that specific text complexity:
- **Single:** One agent for trivial sections.
- **Star:** Specialists (e.g., a Normative Agent and a Semantic Agent) working in parallel, merged by a Lead Agent.
- **Chain:** Sequential refinement where one agent improves the critique of the previous one.
- **Debate:** Two independent reviewers debate their findings, and a Judge Agent consolidates the final critique.
- **Ensemble:** Multiple independent votes synthesized into a consensus.

The Router also dynamically allocates the most cost-effective LLMs (e.g., *Gemma 3 27B IT* for routing and *Gemini 2.5 Flash-Lite* for execution) and generates a highly specialized system prompt tailored to the section's needs.

### 4. Collaborative Execution
The chosen topology is instantiated. The assigned agents collaboratively review the text, outputting structured JSON observations containing exact quotes, identified issues, actionable suggestions, and the classification of the error (Normative or Semantic).

### 5. Metacognitive Evaluation (Evaluator Agent)
A Senior **Evaluator Agent** rigorously inspects the generated review. It scores the critique from 0 to 100 based on four strict criteria:
- **Coverage:** Did it catch the main issues?
- **Specificity:** Are the suggestions actionable?
- **Absence of Fabrication (Hallucination):** Are the pointed errors actually in the original text?
- **Clarity:** Is the feedback easy for the author to understand?

### 6. The Feedback Loop
If the review score falls below the accepted threshold (e.g., 80.0), a conditional edge in LangGraph is triggered. The system enters a **Feedback Loop**, sending the section back to the Router Agent along with the failure context to attempt a new, potentially more robust architecture, up to a maximum of 3 attempts.

### 7. Continuous Learning (Summarizer Agent)
Once a review is approved, the **Summarizer Agent** condenses the original section into a semantic summary. It indexes this summary, along with the successful architecture, the LLMs used, the final score, and the execution cost, back into the ChromaDB. This ensures the system continuously learns and becomes more cost-efficient over time.

### 8. Final Synthesis (Synthesizer Agent)
After all sections have successfully completed their individual LangGraph cycles, the **Synthesizer Agent** collects the approved reviews. It analyzes the manuscript transversally, identifying macro-patterns (e.g., "The methodology does not support the claims made in the conclusion") and generates a cohesive, professional Final Report in Markdown format.

## Technologies Used
- **Language:** Python 3.12+
- **Agent Orchestration:** LangGraph (0.3+)
- **LLM Abstraction & Interoperability:** LiteLLM (Provider-agnostic interface)
- **Vector Database:** ChromaDB (Embedded local execution)
- **PDF Processing:** MinerU, Docling, MarkItDown
- **Data Validation:** Pydantic
- **Configured LLMs:** Gemini 2.5 Flash-Lite, Gemma 3 27B IT, Gemini Embedding 2 (Hosted via Google/Vertex AI).

## Setup and Execution

### Prerequisites
- Python 3.12 installed.
- (Recommended) A dedicated GPU compatible with PyTorch to accelerate deep PDF extraction via *MinerU* or *Docling*.

### Installation
1. Clone this repository.
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows (PowerShell):
   .\venv\Scripts\Activate.ps1
   # On Linux/Mac:
   source venv/bin/activate
   ```
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Create a `.env` file in the project root and add your Google API key to enable the Gemini and Gemma models:
   ```env
   GEMINI_API_KEY=your_google_api_key_here
   ```

### Running the System
To initiate a complete review cycle, run the `main.py` script pointing to your PDF manuscript:

```bash
python main.py path/to/your/document.pdf
```

*(If no arguments are provided, the script will look for a `sample_tcc.pdf` file in the root directory).*

Upon completion, the console will output the full AI examination board report, and a **`relatorio_final.md`** file will be saved in the root directory. 
The granular "thoughts", decisions, and raw JSON outputs from all intra-agent communications are logged and organized by execution IDs in the `logs/agents_responses/` folder for traceability and auditing.

## Project Structure
- `src/agents/`: The personas and logic of the specialized agents (Router, Evaluator, Summarizer, Synthesizer).
- `src/agents/execution/`: The core of the multi-agent topologies (Star, Debate, Chain, Ensemble, Single).
- `src/ingestion/`: Modules responsible for extracting raw PDF text via OCR/GPU and segmenting it into canonical Markdown chapters.
- `src/memory/`: ChromaDB integration and Embedding generation (The RAG module).
- `src/models/`: Pydantic schemas that enforce strict and standardized JSON communication between the AI models.
- `src/orchestration/`: The macro-brain that dictates the state machine (`ReviewState`), conditional edges, and feedback loops controlled by LangGraph.
- `src/config.py`: Centralized configuration for default models, parsers, and quality thresholds.
- `tests/`: A comprehensive suite of integration tests validating the behavior of the LangGraph state machine, the vector database, and individual agent prompting.
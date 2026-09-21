"""A deterministic skill/term lexicon for JD keyword extraction.

No model and no network: terms are matched by normalised phrase and word
boundary. Canonical terms keep the report stable across alias spellings.
"""

from __future__ import annotations

import re
from functools import lru_cache

# canonical -> aliases (canonical itself is always included)
LEXICON: dict[str, list[str]] = {
    "Python": ["python"],
    "C++": ["c++", "cpp"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js"],
    "TypeScript": ["typescript"],
    "SQL": ["sql"],
    "PostgreSQL": ["postgresql", "postgres"],
    "R": [],
    "HTML/CSS": ["html", "css", "html/css"],
    "React": ["react", "react.js", "reactjs"],
    "Node.js": ["node.js", "nodejs", "node"],
    "FastAPI": ["fastapi"],
    "Flask": ["flask"],
    "Django": ["django"],
    "REST APIs": ["rest api", "restful", "rest apis"],
    "GraphQL": ["graphql"],
    "Docker": ["docker", "containerization"],
    "Kubernetes": ["kubernetes", "k8s"],
    "Git": ["git", "version control"],
    "CI/CD": ["ci/cd", "continuous integration", "continuous delivery"],
    "Google Cloud Platform": ["google cloud", "gcp"],
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure"],
    "Linux": ["linux", "unix"],
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "neural network", "neural networks"],
    "LLMs": ["llm", "llms", "large language model", "large language models"],
    "Generative AI": ["generative ai", "genai", "generative"],
    "NLP": ["nlp", "natural language processing"],
    "Computer Vision": ["computer vision", "cv"],
    "RLHF": ["rlhf", "reinforcement learning from human feedback"],
    "Reinforcement Learning": ["reinforcement learning"],
    "Prompt Engineering": ["prompt engineering", "prompting"],
    "RAG": ["rag", "retrieval augmented generation", "retrieval-augmented generation"],
    "Fine-tuning": ["fine-tuning", "finetuning", "fine tuning", "lora", "peft"],
    "PyTorch": ["pytorch", "torch"],
    "TensorFlow": ["tensorflow"],
    "Hugging Face": ["hugging face", "huggingface", "transformers"],
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Matplotlib": ["matplotlib"],
    "XGBoost": ["xgboost"],
    "Data Analysis": ["data analysis", "data analytics", "analytics"],
    "Data Science": ["data science", "data scientist"],
    "Data Engineering": ["data engineering", "data engineer", "etl", "data pipeline", "data pipelines"],
    "Data Visualization": ["data visualization", "data visualisation", "visualization", "dashboard", "tableau", "power bi"],
    "Statistics": ["statistics", "statistical", "hypothesis testing", "confidence interval", "confidence intervals"],
    "Forecasting": ["forecasting", "forecast", "time series", "time-series"],
    "Evaluation": ["evaluation", "eval", "benchmark", "benchmarking", "a/b test", "ab test"],
    "MLOps": ["mlops", "model deployment", "model serving"],
    "Model Deployment": ["model deployment", "deployment", "serving"],
    "Predictive Modeling": ["predictive modeling", "predictive modelling", "predictive model"],
    "Research": ["research", "research scientist", "publication", "publications"],
    "Algorithms": ["algorithms", "data structures"],
    "Optimization": ["optimization", "optimisation"],
    "Security": ["security", "appsec", "guardrails"],
    "Automation": ["automation", "scripting", "automation scripting"],
    "Data Scraping": ["data scraping", "web scraping", "scraping"],
    "Communication": ["communication", "stakeholder", "cross-functional", "collaboration"],
    "Problem Solving": ["problem solving", "problem-solving", "analytical"],
    "Agile": ["agile", "scrum"],
}

# Avoid one/two-letter false positives (e.g. "R", "ML" inside words: handled by
# word boundaries, but short aliases like "js"/"cv" are kept because they are
# commonly used as initials).
MIN_TERM_LEN = 2


def normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("\u2019", "'").replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[\s]+", " ", text)
    return text


@lru_cache(maxsize=1)
def _alias_index() -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for canonical, aliases in LEXICON.items():
        phrases = {canonical.lower(), *[a.lower() for a in aliases]}
        for phrase in phrases:
            if len(phrase) >= MIN_TERM_LEN:
                items.append((phrase, canonical))
    # Longest phrases first so "machine learning" wins over "learning".
    items.sort(key=lambda x: len(x[0]), reverse=True)
    return items


def _pattern(phrase: str) -> re.Pattern[str]:
    escaped = re.escape(phrase)
    return re.compile(rf"(?<![a-z0-9+]){escaped}(?![a-z0-9+])", re.IGNORECASE)


@lru_cache(maxsize=2048)
def _compiled(phrase: str) -> re.Pattern[str]:
    return _pattern(phrase)


def extract_terms(text: str) -> list[str]:
    """Return canonical terms present in text, ordered by first appearance."""
    if not text:
        return []
    norm = normalize(text)
    found: dict[str, int] = {}
    for phrase, canonical in _alias_index():
        m = _compiled(phrase).search(norm)
        if m:
            pos = m.start()
            if canonical not in found or pos < found[canonical]:
                found[canonical] = pos
    return [term for term, _ in sorted(found.items(), key=lambda kv: kv[1])]


def profile_terms(profile) -> list[str]:
    """Canonical terms the master profile genuinely supports."""
    text = " ".join([profile.raw_text, *profile.skill_terms()])
    return extract_terms(text)

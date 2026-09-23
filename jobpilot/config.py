"""Configuration loading.

All user-specific values (profile path, company board tokens, thresholds, caps)
live in a TOML file supplied at runtime. Nothing personal is hardcoded in the
source; :func:`default_config` only defines neutral defaults.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProfileConfig:
    path: str = ""
    style_template: str = ""
    pdflatex: str = "pdflatex"
    pdftotext: str = "pdftotext"
    compile_timeout: int = 120
    # A student resume must fit this many pages (1 by default). The pipeline
    # measures the compiled PDF and, when over, reduces deterministically and
    # recompiles within ``resume_fit_attempts`` bounded attempts. The default
    # covers every entry of the ladder in ``pipeline._FIT_VARIANTS`` so no rung
    # is unreachable; lower it to bound compile cost on slow engines. If it
    # still cannot fit, the posting is queued for review with the measured count
    # and flagged on the presentation card rather than shipping an over-long
    # resume.
    resume_page_limit: int = 1
    resume_fit_attempts: int = 9


@dataclass
class OutputConfig:
    dir: str = "out"
    database: str = "jobpilot.db"


@dataclass
class SourceConfig:
    name: str = ""
    enabled: bool = True
    tokens: list[str] = field(default_factory=list)
    options: dict[str, Any] = field(default_factory=dict)


# Sources whose terms forbid automation (or which block non-browser clients).
# They are never scraped and never authenticated; instead the pipeline surfaces a
# configured search link for a human and accepts a posting the human adds by
# hand. A posting from one of these sources is always review-only: the pipeline
# prepares the tailored packet and the direct link, and the human submits it.
DEFAULT_LINK_OUT_SOURCES: dict[str, dict[str, str]] = {
    "internshala": {
        "label": "Internshala",
        "search_url": "https://internshala.com/internships/machine-learning-internship",
        "terms_note": (
            "Terms expressly prohibit automated extraction and list AI/ML training; "
            "robots blocks Anthropic/OpenAI crawlers. Best source for the Jan-May window."
        ),
    },
    "naukri": {
        "label": "Naukri",
        "search_url": "https://www.naukri.com/machine-learning-intern-jobs",
        "terms_note": "Listings API demands an app/system id then a reCAPTCHA; terms and robots forbid automation.",
    },
    "linkedin": {
        "label": "LinkedIn",
        "search_url": "https://www.linkedin.com/jobs/search/?keywords=intern&location=India",
        "terms_note": (
            "robots and the user agreement forbid automated access; jobpilot's optional "
            "reader is read-only and best-effort, and never authenticates."
        ),
    },
    "wellfound": {
        "label": "Wellfound",
        "search_url": "https://wellfound.com/location/india",
        "terms_note": "Terms ban automated harvesting and scraping; no public API.",
    },
    "hiringcafe": {
        "label": "HiringCafe",
        "search_url": "https://hiringcafe.com/jobs",
        "terms_note": "Cloudflare-blocked to non-browser clients and terms forbid reproducing listings.",
    },
    "a16z": {
        "label": "a16z Portfolio Jobs",
        "search_url": "https://portfoliojobs.a16z.com/jobs",
        "terms_note": "Consider's terms forbid robots/scrapers; the search API needs a CSRF token and cookies.",
    },
    "peakxv": {
        "label": "Peak XV (Consider)",
        "search_url": "https://careers.peakxv.com/jobs",
        "terms_note": (
            "Same Consider terms; strong India internship inventory, but the endpoint "
            "needs CSRF and cookies, so it is browse-only."
        ),
    },
    "remote_co": {
        "label": "Remote.co",
        "search_url": "https://remote.co/remote-jobs/",
        "terms_note": "Terms forbid scraping and redistribution of listings; Cloudflare-blocked.",
    },
}

#: Automated, read-only discovery adapters that are enabled by default.
DEFAULT_DISCOVERY_SOURCES = (
    "greenhouse",
    "lever",
    "ashby",
    "workable",
    "himalayas",
    "unstop",
    "workable_global",
    "themuse",
)


@dataclass
class LinkOutSource:
    name: str = ""
    label: str = ""
    search_url: str = ""
    terms_note: str = ""
    enabled: bool = True


@dataclass
class LinkOutConfig:
    enabled: bool = True
    sources: dict[str, LinkOutSource] = field(default_factory=dict)


@dataclass
class FilterConfig:
    internship_keywords: list[str] = field(
        default_factory=lambda: [
            "intern",
            "internship",
            "co-op",
            "coop",
            "summer analyst",
        ]
    )
    fulltime_reject_keywords: list[str] = field(
        default_factory=lambda: ["full-time", "full time", "fulltime", "permanent", "experienced hire"]
    )
    seniority_reject_keywords: list[str] = field(
        default_factory=lambda: [
            "senior",
            "staff",
            "principal",
            "lead ",
            "manager",
            "director",
            "head of",
            "vp ",
            "vice president",
            "architect",
        ]
    )
    india_keywords: list[str] = field(
        default_factory=lambda: [
            "india",
            "bengaluru",
            "bangalore",
            "hyderabad",
            "pune",
            "mumbai",
            "delhi",
            "noida",
            "gurgaon",
            "gurugram",
            "chennai",
            "kolkata",
            "ahmedabad",
            "jaipur",
            "remote - india",
            "remote, india",
            "ind",
        ]
    )
    remote_keywords: list[str] = field(
        default_factory=lambda: [
            "remote",
            "anywhere",
            "worldwide",
            "global",
            "work from home",
            "wfh",
            "distributed",
            "telecommut",
        ]
    )
    location_reject_keywords: list[str] = field(
        default_factory=lambda: [
            "must be based in the us",
            "us work authorization",
            "authorized to work in the us",
            "requires us citizenship",
            "security clearance",
        ]
    )
    allow_unknown_window: bool = False
    allow_onsite_abroad: bool = False
    allow_unknown_location: bool = False
    window_start_month: int = 1
    window_end_month: int = 6


@dataclass
class MatchConfig:
    shortlist_threshold: float = 0.42
    strong_threshold: float = 0.68
    # To be auto-apply-eligible (`strong`), a posting's ``role_relevance`` must
    # reach this minimum. Role relevance is the overlap between the posting's
    # title/description and the configured ``target_terms`` domains, so this
    # floor is how the *search target* is enforced: retarget ``target_terms``
    # for a different search and set the floor accordingly. A posting that
    # clears ``strong_threshold`` but sits below the floor is capped to
    # ``shortlist`` (tailored + review-only), never ``strong`` (auto-apply).
    strong_min_role_relevance: float = 0.5
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "skill_coverage": 0.45,
            "role_relevance": 0.25,
            "location_fit": 0.15,
            "window_fit": 0.10,
            "seniority_fit": 0.05,
        }
    )
    target_terms: dict[str, list[str]] = field(
        default_factory=lambda: {
            "ai_ml": [
                "machine learning",
                "deep learning",
                "artificial intelligence",
                "ai engineer",
                "ai intern",
                "ai research",
                "ai scientist",
                "ai developer",
                "ai/ml",
                "ai ml",
                "applied ai",
                "llm",
                "llms",
                "generative",
                "rag",
                "nlp",
                "pytorch",
                "tensorflow",
                "rlhf",
                "evaluation",
                "data science",
                "data scientist",
                "forecasting",
                "time series",
            ],
            "software": [
                "python",
                "software engineer",
                "backend",
                "api",
                "fastapi",
                "flask",
                "sql",
                "postgres",
                "data engineer",
                "docker",
            ],
            "research": ["research", "research scientist", "publication", "benchmark", "experiment"],
        }
    )
    required_sections: list[str] = field(
        default_factory=lambda: ["Education", "Experience", "Projects", "Technical Skills"]
    )
    require_parseable: bool = True
    # Minimum fraction of the JD's supported keywords that must survive into the
    # compiled PDF; below this the resume is treated as not parseable.
    min_keyword_survival: float = 0.5
    max_projects: int = 4
    include_positions: bool = False
    include_non_ai_experience: bool = False
    bold_metrics: bool = True


@dataclass
class PresentConfig:
    """Selection and rendering for ``jobpilot present``.

    This is a *presentation* layer only: it filters and orders what the pipeline
    already produced. It never re-scores, never invents resume content and never
    submits anything.

    ``technical_domains`` names the ``[match.target_terms]`` domains that count
    as a genuine technical / AI-ML fit. A domain listed in ``guarded_domains``
    (``research`` by default) only counts when the posting also matches at least
    one ``core_skills`` term, because "research" alone matches design research,
    policy research and market research as readily as ML research. Retarget the
    presented role set by changing ``technical_domains``, ``min_role_relevance``
    and ``exclude_terms`` - never by hardcoding a role in code.
    """

    # Directory for the generated page, resolved relative to ``[output].dir``
    # (an absolute path is used as-is). The page is ``<out_dir>/index.html``.
    out_dir: str = "present"
    min_role_relevance: float = 0.5
    borderline_role_relevance: float = 0.4
    technical_domains: list[str] = field(
        default_factory=lambda: ["ai_ml", "software", "research"]
    )
    guarded_domains: list[str] = field(default_factory=lambda: ["research"])
    core_skills: list[str] = field(
        default_factory=lambda: [
            "Python", "C++", "Java", "JavaScript", "TypeScript", "SQL",
            "PostgreSQL", "R", "HTML/CSS", "React", "Node.js", "FastAPI",
            "Flask", "Django", "REST APIs", "GraphQL", "Docker", "Kubernetes",
            "Git", "CI/CD", "Google Cloud Platform", "AWS", "Azure", "Linux",
            "Machine Learning", "Deep Learning", "LLMs", "Generative AI", "NLP",
            "Computer Vision", "RLHF", "Reinforcement Learning",
            "Prompt Engineering", "RAG", "Fine-tuning", "PyTorch", "TensorFlow",
            "Hugging Face", "Scikit-learn", "pandas", "NumPy", "Matplotlib",
            "XGBoost", "Data Analysis", "Data Science", "Data Engineering",
            "Data Visualization", "Statistics", "Forecasting", "MLOps",
            "Model Deployment", "Predictive Modeling", "Algorithms",
        ]
    )
    # Non-technical role keywords excluded from the presented list even if a
    # posting's role relevance clears the floor. Matched against the title as a
    # whole-word phrase, so an ambiguous word only excludes the non-technical
    # sense: "graphic design" is excluded but "AI system design" is not,
    # "business operations" is excluded but "machine learning operations" is
    # not, and "visual design" is excluded but "data visualization" is not.
    # Spell out inflections ("recruiter" as well as "recruiting") rather than
    # relying on prefix matching, which would drop genuine technical roles.
    # Configurable.
    exclude_terms: list[str] = field(
        default_factory=lambda: [
            "graphic design", "product design", "ux design", "ui design",
            "visual design", "interaction design", "web design", "motion design",
            "brand design", "designer", "ux", "ui", "user experience", "graphic",
            "brand", "communication", "communications", "content", "video",
            "editor", "editorial", "writer", "writing", "copywriter",
            "copywriting", "social media", "marketing", "seo", "advertising",
            "advertisement", "advertiser", "campaign", "demand generation",
            "lead generation", "data entry", "human resources", "human resource",
            "hr", "recruiting", "recruiter", "recruitment", "talent", "hiring",
            "sales", "business development", "accounting", "accountant",
            "account management", "account executive", "finance", "bookkeeping",
            "taxation", "customer success", "customer support",
            "customer service", "campus ambassador", "campus representative",
            "community", "partnership", "sponsorship", "fundraising",
            "product management", "project management", "product marketing",
            "business operations", "people operations", "receptionist",
            "hotel management", "voice over", "music", "acting", "tutor",
            "teacher", "counsel", "counseling", "counselor", "psychology",
            "correspondent",
        ]
    )
    max_borderline: int = 8


@dataclass
class ApplyConfig:
    enabled: bool = True
    auto_apply_strong: bool = True
    adapter: str = "auto"
    daily_cap: int = 5
    answers_file: str = "answers.toml"
    submission: dict[str, Any] = field(default_factory=dict)


@dataclass
class LinkedInConfig:
    enabled: bool = False
    keywords: str = "intern"
    location: str = "India"
    max_pages: int = 1
    requests_per_second: float = 0.2
    timeout: float = 20.0
    max_results: int = 25


@dataclass
class Config:
    profile: ProfileConfig = field(default_factory=ProfileConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    sources: dict[str, SourceConfig] = field(default_factory=dict)
    filter: FilterConfig = field(default_factory=FilterConfig)
    match: MatchConfig = field(default_factory=MatchConfig)
    present: PresentConfig = field(default_factory=PresentConfig)
    apply: ApplyConfig = field(default_factory=ApplyConfig)
    linkedin: LinkedInConfig = field(default_factory=LinkedInConfig)
    link_out: LinkOutConfig = field(default_factory=LinkOutConfig)
    config_path: str = ""
    base_dir: str = ""

    def resolve(self, path: str) -> str:
        """Resolve a possibly-relative path against the config file's directory."""
        if not path:
            return path
        p = Path(path)
        if p.is_absolute():
            return str(p)
        base = Path(self.base_dir) if self.base_dir else Path.cwd()
        return str((base / p).resolve())

    def source(self, name: str) -> SourceConfig | None:
        return self.sources.get(name)


def default_config() -> Config:
    cfg = Config()
    for name in DEFAULT_DISCOVERY_SOURCES:
        cfg.sources[name] = SourceConfig(name=name, enabled=True)
    cfg.link_out = LinkOutConfig(
        sources={
            name: LinkOutSource(name=name, **spec)
            for name, spec in DEFAULT_LINK_OUT_SOURCES.items()
        }
    )
    return cfg


def _overlay_link_out(cfg: Config, raw: dict[str, Any]) -> None:
    spec = raw.get("link_out")
    if not isinstance(spec, dict):
        return
    if "enabled" in spec:
        cfg.link_out.enabled = bool(spec["enabled"])
    for name, entry in (spec.get("sources") or {}).items():
        if not isinstance(entry, dict):
            continue
        existing = cfg.link_out.sources.get(name, LinkOutSource(name=name))
        existing.name = name
        for key in ("label", "search_url", "terms_note"):
            if key in entry:
                setattr(existing, key, str(entry[key]))
        if "enabled" in entry:
            existing.enabled = bool(entry["enabled"])
        cfg.link_out.sources[name] = existing


def _overlay_sources(cfg: Config, raw: dict[str, Any]) -> None:
    raw_sources = raw.get("sources", {})
    for name, spec in raw_sources.items():
        if not isinstance(spec, dict):
            continue
        existing = cfg.sources.get(name, SourceConfig(name=name))
        existing.name = name
        if "enabled" in spec:
            existing.enabled = bool(spec["enabled"])
        if "tokens" in spec:
            existing.tokens = [str(t) for t in spec["tokens"]]
        known = {"enabled", "tokens"}
        existing.options = {k: v for k, v in spec.items() if k not in known}
        cfg.sources[name] = existing


def _update_dataclass(obj: Any, raw: dict[str, Any]) -> None:
    for key, value in raw.items():
        if hasattr(obj, key):
            setattr(obj, key, value)


def load_config(path: str | os.PathLike[str]) -> Config:
    p = Path(path)
    with p.open("rb") as fh:
        raw = tomllib.load(fh)

    cfg = default_config()
    cfg.config_path = str(p.resolve())
    cfg.base_dir = str(p.resolve().parent)

    if "profile" in raw:
        _update_dataclass(cfg.profile, raw["profile"])
    if "output" in raw:
        _update_dataclass(cfg.output, raw["output"])
    if "filter" in raw:
        _update_dataclass(cfg.filter, raw["filter"])
    if "match" in raw:
        _update_dataclass(cfg.match, raw["match"])
    if "present" in raw:
        _update_dataclass(cfg.present, raw["present"])
    if "apply" in raw:
        _update_dataclass(cfg.apply, raw["apply"])
    if "linkedin" in raw:
        _update_dataclass(cfg.linkedin, raw["linkedin"])
    _overlay_sources(cfg, raw)
    _overlay_link_out(cfg, raw)
    return cfg

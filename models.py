from dataclasses import dataclass, field


@dataclass
class ScrapeResult:
    jobs: list
    classification: str
    diagnostic: dict = field(default_factory=dict)
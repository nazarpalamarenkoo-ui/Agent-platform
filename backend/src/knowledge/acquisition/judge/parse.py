from collections import Counter

from pydantic import ValidationError

from src.knowledge.acquisition.judge.exceptions import JudgeValidationError
from src.knowledge.acquisition.judge.models import JudgeItem, JudgeResponse

MAX_IDENTICAL_REASONS = 1


def parse(raw: dict, keys: list[str]) -> list[JudgeItem]:
    try:
        response = JudgeResponse.model_validate(raw)
    except ValidationError as e:
        raise JudgeValidationError(f"Invalid judge response: {e}") from e

    items = response.results
    returned_keys = [item.key for item in items]

    counts = Counter(returned_keys)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    missing = sorted(set(keys) - set(returned_keys))
    unexpected = sorted(set(returned_keys) - set(keys))

    if duplicates or missing or unexpected:
        raise JudgeValidationError(
            f"Key mismatch: missing={missing}, "
            f"unexpected={unexpected}, duplicates={duplicates}"
        )

    _check_reason_diversity(items)

    return items


def _check_reason_diversity(items: list[JudgeItem]) -> None:
    if len(items) <= MAX_IDENTICAL_REASONS:
        return

    normalized_reasons = [item.reason.strip().lower() for item in items]
    counts = Counter(normalized_reasons)

    repeated = {
        reason: count
        for reason, count in counts.items()
        if count > MAX_IDENTICAL_REASONS
    }

    if repeated:
        worst_reason, worst_count = max(repeated.items(), key=lambda kv: kv[1])
        raise JudgeValidationError(
            f"Judge reused the same reason for {worst_count} different "
            f'documents in one batch ("{worst_reason[:80]}..."), '
            f"which means it likely copied a template instead of evaluating "
            f"each document individually."
        )
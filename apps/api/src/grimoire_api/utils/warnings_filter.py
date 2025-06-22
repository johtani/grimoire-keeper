"""警告フィルタ設定."""

import warnings

# Pydantic deprecation警告を抑制
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message="Support for class-based `config` is deprecated.*",
)

# SQLite datetime adapter警告を抑制
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    message="The default datetime adapter is deprecated.*",
)

# RuntimeWarning (coroutine未await)を抑制
warnings.filterwarnings(
    "ignore",
    category=RuntimeWarning,
    message="coroutine.*was never awaited",
)
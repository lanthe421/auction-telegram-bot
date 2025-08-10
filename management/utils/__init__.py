"""
Утилиты для управления системой
"""

from .cache_manager import (
    cache_manager,
    cache_result,
    start_cache_cleanup,
    stop_cache_cleanup,
)

# from .diagnostics import get_system_report, run_full_diagnostics
# from .image_optimizer import get_media_usage_stats, media_manager, optimize_images
# from .index_manager import (
#     analyze_indexes,
#     create_recommended_indexes,
#     get_index_stats,
#     index_manager,
# )
# from .performance_monitor import (
#     get_performance_alerts,
#     get_performance_summary,
#     get_system_health,
#     run_system_diagnostics,
#     start_performance_monitoring,
#     stop_performance_monitoring,
# )
# from .query_optimizer import analyze_query_performance, get_query_stats, query_optimizer

__all__ = [
    # Cache management
    "cache_manager",
    "cache_result",
    "start_cache_cleanup",
    "stop_cache_cleanup",
]

"""
Репозитории для работы с базой данных
"""

from .bids import BidsRepository
from .lots import LotsRepository
from .users import UsersRepository

__all__ = ["LotsRepository", "BidsRepository", "UsersRepository"]


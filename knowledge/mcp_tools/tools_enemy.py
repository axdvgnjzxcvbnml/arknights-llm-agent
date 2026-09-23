"""敌人相关 MCP 工具。数据来自 PRTS 敌人图鉴 JSON，evidence=fact。"""

from pydantic import ValidationError

from . import schemas as S
from .service import KnowledgeService, get_default_service

__all__ = ["query_enemy"]


def query_enemy(name, level=None, service=None):
    # type: (str, int, KnowledgeService) -> S.EnemyOut
    """查询敌人属性，按级别返回（level 缺省返回全部级别）。"""
    try:
        S.EnemyIn(name=name if name is not None else "", level=level)
    except ValidationError:
        return S.EnemyOut(found=False,
                          message="level 必须是整数级别（0 起），收到：%r" % (level,))
    svc = service or get_default_service()
    return svc.query_enemy(name, level=level)

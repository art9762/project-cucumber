"""GET/POST /categories* и POST /classify — роутер дерева категорий (Фаза 1)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.auth.dependencies import get_current_user, require_role
from analysis.api.category_schemas import (
    ApproveResponse,
    CategoryOut,
    CategoryTreeNode,
    ClassifyRunOut,
    RejectResponse,
)
from analysis.classify.categories import (
    delete_category,
    list_pending,
    load_category_tree,
    set_approved,
)
from analysis.classify.models import CategoryNode
from analysis.storage.db import (
    get_analysis_session,
    get_analysis_sessionmaker,
    get_read_sessionmaker,
)

router = APIRouter(tags=["categories"])


def _node_to_out(node: CategoryNode) -> CategoryOut:
    """Конвертировать CategoryNode в CategoryOut (UUID → str)."""
    return CategoryOut(
        id=str(node.id),
        slug=node.slug,
        title=node.title,
        parent_id=str(node.parent_id) if node.parent_id is not None else None,
        approved=node.approved,
    )


def _build_tree(nodes: list[CategoryNode]) -> list[CategoryTreeNode]:
    """Построить вложенное дерево CategoryTreeNode из плоского списка."""
    tree_nodes: dict[uuid.UUID, CategoryTreeNode] = {
        n.id: CategoryTreeNode(
            id=str(n.id),
            slug=n.slug,
            title=n.title,
            approved=n.approved,
        )
        for n in nodes
    }

    children_map: dict[uuid.UUID | None, list[uuid.UUID]] = defaultdict(list)
    for n in nodes:
        children_map[n.parent_id].append(n.id)

    for parent_id, child_ids in children_map.items():
        if parent_id is not None and parent_id in tree_nodes:
            tree_nodes[parent_id].children = [tree_nodes[c] for c in child_ids]

    roots = [tree_nodes[n.id] for n in nodes if n.parent_id is None]
    return roots


@router.get("/categories", response_model=list[CategoryTreeNode])
async def get_category_tree(
    session: AsyncSession = Depends(get_analysis_session),
    _user=Depends(get_current_user),
) -> list[CategoryTreeNode]:
    """Вернуть дерево всех категорий (approved и pending), вложенное по parent_id."""
    nodes = await load_category_tree(session)
    return _build_tree(nodes)


@router.get("/categories/pending", response_model=list[CategoryOut])
async def get_pending_categories(
    session: AsyncSession = Depends(get_analysis_session),
    _user=Depends(get_current_user),
) -> list[CategoryOut]:
    """Вернуть список неутверждённых категорий (очередь модерации)."""
    nodes = await list_pending(session)
    return [_node_to_out(n) for n in nodes]


@router.post("/categories/{id}/approve", response_model=ApproveResponse)
async def approve_category(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_analysis_session),
    _user=Depends(require_role("admin")),
) -> ApproveResponse:
    """Утвердить категорию. 404, если категория не найдена."""
    node = await set_approved(session, id, True)
    if node is None:
        raise HTTPException(status_code=404, detail="Category not found")
    await session.commit()
    return ApproveResponse(ok=True, id=str(node.id), approved=node.approved)


@router.post("/categories/{id}/reject", response_model=RejectResponse)
async def reject_category(
    id: uuid.UUID,
    session: AsyncSession = Depends(get_analysis_session),
    _user=Depends(require_role("admin")),
) -> RejectResponse:
    """Удалить категорию (reject). 404, если категория не найдена."""
    deleted = await delete_category(session, id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Category not found")
    await session.commit()
    return RejectResponse(ok=True, id=str(id))


@router.post("/classify", response_model=ClassifyRunOut)
async def classify(
    limit: Optional[int] = Query(default=None, ge=1),
    _user=Depends(require_role("admin")),
) -> ClassifyRunOut:
    """Запустить прогон классификации новых items. Возвращает статистику прогона."""
    from analysis.classify.classifier import run_classification  # ленивый импорт
    from analysis.trinity import get_trinity_client  # ленивый импорт

    stats = await run_classification(
        read_sessionmaker=get_read_sessionmaker(),
        analysis_sessionmaker=get_analysis_sessionmaker(),
        trinity=get_trinity_client(),
        limit=limit,
    )
    return ClassifyRunOut(
        seen=stats.seen,
        classified=stats.classified,
        suggested=stats.suggested,
        failed=stats.failed,
        errors=stats.errors,
    )

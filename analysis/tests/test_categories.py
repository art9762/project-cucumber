"""Тесты репозитория категорий (Фаза 1).

БД-тесты на in-memory SQLite через фикстуру ``analysis_sessionmaker``.
Алembic-миграции в SQLite не гоняются — категории сидируются вручную в каждом тесте.
"""

from __future__ import annotations

import uuid

import pytest

from analysis.classify.categories import (
    delete_category,
    ensure_subcategory,
    get_by_slug,
    list_pending,
    load_approved_top_level,
    load_category_tree,
    set_approved,
)
from analysis.storage.orm import CategoryORM


# ---------------------------------------------------------------------------
# Вспомогательные фабрики
# ---------------------------------------------------------------------------

def _cat(
    slug: str,
    title: str,
    *,
    approved: bool = True,
    parent_id: uuid.UUID | None = None,
) -> CategoryORM:
    """Минимальная фабрика CategoryORM для тестового сидинга."""
    return CategoryORM(slug=slug, title=title, approved=approved, parent_id=parent_id)


# ---------------------------------------------------------------------------
# load_approved_top_level
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_approved_top_level_excludes_children(analysis_sessionmaker) -> None:
    """load_approved_top_level возвращает только approved верхнего уровня."""
    async with analysis_sessionmaker() as session:
        parent = _cat("tech", "Технологии", approved=True)
        child = _cat("ai", "ИИ", approved=True)
        unapproved = _cat("misc", "Разное", approved=False)
        session.add_all([parent, child, unapproved])
        await session.flush()
        # Установить parent_id у child после flush, чтобы иметь id родителя
        child.parent_id = parent.id
        await session.commit()

    async with analysis_sessionmaker() as session:
        nodes = await load_approved_top_level(session)

    slugs = {n.slug for n in nodes}
    assert "tech" in slugs
    assert "ai" not in slugs      # у него parent_id, не верхний уровень
    assert "misc" not in slugs    # не approved


@pytest.mark.asyncio
async def test_load_approved_top_level_empty(analysis_sessionmaker) -> None:
    """Пустая БД — пустой список."""
    async with analysis_sessionmaker() as session:
        nodes = await load_approved_top_level(session)
    assert nodes == []


# ---------------------------------------------------------------------------
# load_category_tree
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_load_category_tree_returns_all(analysis_sessionmaker) -> None:
    """load_category_tree возвращает все записи независимо от approved."""
    async with analysis_sessionmaker() as session:
        session.add_all([
            _cat("a", "A", approved=True),
            _cat("b", "B", approved=False),
        ])
        await session.commit()

    async with analysis_sessionmaker() as session:
        nodes = await load_category_tree(session)

    assert {n.slug for n in nodes} == {"a", "b"}


# ---------------------------------------------------------------------------
# get_by_slug
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_by_slug_hit(analysis_sessionmaker) -> None:
    """get_by_slug возвращает CategoryNode при совпадении."""
    async with analysis_sessionmaker() as session:
        session.add(_cat("science", "Наука"))
        await session.commit()

    async with analysis_sessionmaker() as session:
        node = await get_by_slug(session, "science")

    assert node is not None
    assert node.slug == "science"
    assert node.title == "Наука"


@pytest.mark.asyncio
async def test_get_by_slug_miss(analysis_sessionmaker) -> None:
    """get_by_slug возвращает None для несуществующего slug."""
    async with analysis_sessionmaker() as session:
        node = await get_by_slug(session, "nonexistent")
    assert node is None


# ---------------------------------------------------------------------------
# ensure_subcategory
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_subcategory_creates_unapproved_child(analysis_sessionmaker) -> None:
    """ensure_subcategory создаёт дочерний узел с approved=False."""
    async with analysis_sessionmaker() as session:
        session.add(_cat("tech", "Технологии"))
        await session.commit()

    async with analysis_sessionmaker() as session:
        node = await ensure_subcategory(session, parent_slug="tech", slug="llm", title="LLM")
        await session.commit()

    assert node.slug == "llm"
    assert node.approved is False
    assert node.parent_id is not None


@pytest.mark.asyncio
async def test_ensure_subcategory_parent_id_matches(analysis_sessionmaker) -> None:
    """ensure_subcategory назначает parent_id = id родителя."""
    async with analysis_sessionmaker() as session:
        parent_orm = _cat("tech", "Технологии")
        session.add(parent_orm)
        await session.flush()
        parent_id = parent_orm.id
        await session.commit()

    async with analysis_sessionmaker() as session:
        node = await ensure_subcategory(session, parent_slug="tech", slug="llm", title="LLM")
        await session.commit()

    assert node.parent_id == parent_id


@pytest.mark.asyncio
async def test_ensure_subcategory_idempotent(analysis_sessionmaker) -> None:
    """Повторный вызов с тем же slug возвращает существующий узел без дублирования."""
    async with analysis_sessionmaker() as session:
        session.add(_cat("tech", "Технологии"))
        await session.commit()

    async with analysis_sessionmaker() as session:
        node1 = await ensure_subcategory(session, parent_slug="tech", slug="llm", title="LLM")
        await session.commit()

    async with analysis_sessionmaker() as session:
        node2 = await ensure_subcategory(session, parent_slug="tech", slug="llm", title="LLM другое")
        await session.commit()

    # Один и тот же id, title не изменился
    assert node1.id == node2.id
    assert node2.title == "LLM"


@pytest.mark.asyncio
async def test_ensure_subcategory_unknown_parent_raises(analysis_sessionmaker) -> None:
    """ensure_subcategory бросает ValueError при отсутствии родителя."""
    async with analysis_sessionmaker() as session:
        with pytest.raises(ValueError, match="tech"):
            await ensure_subcategory(session, parent_slug="tech", slug="llm", title="LLM")


@pytest.mark.asyncio
async def test_ensure_subcategory_does_not_flip_approved(analysis_sessionmaker) -> None:
    """Если slug уже существует с approved=True, ensure_subcategory не меняет флаг."""
    async with analysis_sessionmaker() as session:
        parent = _cat("tech", "Технологии")
        existing = _cat("llm", "LLM", approved=True)
        session.add_all([parent, existing])
        await session.flush()
        existing.parent_id = parent.id
        await session.commit()

    async with analysis_sessionmaker() as session:
        node = await ensure_subcategory(
            session, parent_slug="tech", slug="llm", title="LLM новый заголовок"
        )

    assert node.approved is True  # флаг не изменился


# ---------------------------------------------------------------------------
# list_pending
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_pending_returns_unapproved_only(analysis_sessionmaker) -> None:
    """list_pending возвращает только approved=False."""
    async with analysis_sessionmaker() as session:
        session.add_all([
            _cat("approved-one", "Утверждённая", approved=True),
            _cat("pending-one", "В ожидании 1", approved=False),
            _cat("pending-two", "В ожидании 2", approved=False),
        ])
        await session.commit()

    async with analysis_sessionmaker() as session:
        nodes = await list_pending(session)

    slugs = {n.slug for n in nodes}
    assert slugs == {"pending-one", "pending-two"}


@pytest.mark.asyncio
async def test_list_pending_empty_when_all_approved(analysis_sessionmaker) -> None:
    """Если все approved=True — очередь пуста."""
    async with analysis_sessionmaker() as session:
        session.add(_cat("only", "Единственная", approved=True))
        await session.commit()

    async with analysis_sessionmaker() as session:
        nodes = await list_pending(session)

    assert nodes == []


# ---------------------------------------------------------------------------
# set_approved
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_approved_flips_flag_to_true(analysis_sessionmaker) -> None:
    """set_approved(True) переводит pending-узел в approved."""
    async with analysis_sessionmaker() as session:
        cat = _cat("pending", "Ожидает", approved=False)
        session.add(cat)
        await session.flush()
        cat_id = cat.id
        await session.commit()

    async with analysis_sessionmaker() as session:
        node = await set_approved(session, cat_id, approved=True)
        await session.commit()

    assert node is not None
    assert node.approved is True
    assert node.id == cat_id


@pytest.mark.asyncio
async def test_set_approved_flips_flag_to_false(analysis_sessionmaker) -> None:
    """set_approved(False) переводит утверждённый узел обратно в pending."""
    async with analysis_sessionmaker() as session:
        cat = _cat("approved", "Утверждённая", approved=True)
        session.add(cat)
        await session.flush()
        cat_id = cat.id
        await session.commit()

    async with analysis_sessionmaker() as session:
        node = await set_approved(session, cat_id, approved=False)
        await session.commit()

    assert node is not None
    assert node.approved is False


@pytest.mark.asyncio
async def test_set_approved_missing_id_returns_none(analysis_sessionmaker) -> None:
    """set_approved возвращает None для несуществующего id."""
    async with analysis_sessionmaker() as session:
        result = await set_approved(session, uuid.uuid4(), approved=True)

    assert result is None


# ---------------------------------------------------------------------------
# delete_category
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_category_true_when_present(analysis_sessionmaker) -> None:
    """delete_category возвращает True и удаляет запись."""
    async with analysis_sessionmaker() as session:
        cat = _cat("to-delete", "Для удаления")
        session.add(cat)
        await session.flush()
        cat_id = cat.id
        await session.commit()

    async with analysis_sessionmaker() as session:
        deleted = await delete_category(session, cat_id)
        await session.commit()

    assert deleted is True

    # Убеждаемся, что запись удалена
    async with analysis_sessionmaker() as session:
        node = await get_by_slug(session, "to-delete")
    assert node is None


@pytest.mark.asyncio
async def test_delete_category_false_when_absent(analysis_sessionmaker) -> None:
    """delete_category возвращает False для несуществующего id."""
    async with analysis_sessionmaker() as session:
        result = await delete_category(session, uuid.uuid4())

    assert result is False

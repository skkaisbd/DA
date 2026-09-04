"""
Pagination utility for FastAPI + Motor/MongoDB
Usage:
    from utils.pagination import paginate

    @router.get("/items")
    async def list_items(
        skip: int = Query(0, ge=0, description="Number of records to skip"),
        limit: int = Query(20, ge=1, le=200, description="Max records to return"),
        ...
    ):
        q = {"active": True}
        return await paginate(db.items, q, skip, limit, sort=[("created_at", -1)])

Returns:
    {
        "total": 150,
        "skip": 0,
        "limit": 20,
        "has_more": True,
        "items": [...]
    }
"""
from motor.motor_asyncio import AsyncIOMotorCollection
from auth import serialize_doc
from typing import Optional


async def paginate(
    collection: AsyncIOMotorCollection,
    query: dict,
    skip: int = 0,
    limit: int = 20,
    sort: Optional[list] = None,
    projection: Optional[dict] = None,
    post_process=None,
) -> dict:
    """
    Standard pagination helper. Returns total count + paginated items.
    
    Args:
        collection: Motor collection
        query: MongoDB filter dict
        skip: number of records to skip (offset)
        limit: max records to return
        sort: list of (field, direction) tuples, e.g. [("created_at", -1)]
        projection: MongoDB projection dict (defaults to {"_id": 0})
        post_process: optional async callable(db, items) -> items for enrichment

    Returns:
        {"total": int, "skip": int, "limit": int, "has_more": bool, "items": list}
    """
    if projection is None:
        projection = {"_id": 0}

    total = await collection.count_documents(query)

    cursor = collection.find(query, projection)
    if sort:
        cursor = cursor.sort(sort)
    cursor = cursor.skip(skip).limit(limit)
    items = await cursor.to_list(length=10000)

    if post_process:
        items = await post_process(items)

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total,
        "items": serialize_doc(items),
    }

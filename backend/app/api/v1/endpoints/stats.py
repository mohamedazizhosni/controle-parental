from fastapi import APIRouter, Depends, HTTPException
from bson import ObjectId
from datetime import datetime, timedelta
from collections import defaultdict
from ....db.mongodb import get_db
from .auth import get_current_user

router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get("/{child_id}")
async def get_child_stats(child_id: str, current_user = Depends(get_current_user), days: int = 7):
    db = get_db()
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child id")
    profile = await db.children.find_one({"_id": ObjectId(child_id), "parent_email": current_user["email"]})
    if not profile:
        raise HTTPException(404, "Child not found")
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days-1)
    
    pipeline = [
        {"$match": {
            "child_id": child_id,
            "timestamp": {"$gte": start_date, "$lte": end_date}
        }},
        {"$group": {
            "_id": {
                "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                "category": "$category"
            },
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.date": 1}}
    ]
    
    cursor = db.history.aggregate(pipeline)
    results = await cursor.to_list(length=None)
    
    daily_data = defaultdict(lambda: {"total": 0, "categories": defaultdict(int)})
    for item in results:
        date = item["_id"]["date"]
        category = item["_id"]["category"] or "unknown"
        count = item["count"]
        daily_data[date]["total"] += count
        daily_data[date]["categories"][category] = count
    
    dates = sorted(daily_data.keys())
    totals = [daily_data[d]["total"] for d in dates]
    categories_set = set()
    for d in daily_data.values():
        categories_set.update(d["categories"].keys())
    categories = sorted(categories_set)
    
    category_series = {cat: [] for cat in categories}
    for date in dates:
        for cat in categories:
            category_series[cat].append(daily_data[date]["categories"].get(cat, 0))
    
    return {
        "child_id": child_id,
        "child_name": profile["name"],
        "dates": dates,
        "totals": totals,
        "categories": categories,
        "category_series": category_series
    }

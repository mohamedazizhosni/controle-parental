"""
Blacklist partagée — catégories → domaines (statique + dynamique via Squid/TF-IDF)
GET  /api/v1/blocklist/domains/{child_id}/agent  → liste pour l'agent Android
POST /api/v1/blocklist/dynamic/add               → Squid/Windows ajoute un domaine découvert (JWT)
POST /api/v1/blocklist/dynamic/add_internal      → Squid/Windows ajoute un domaine (clé interne Docker)
GET  /api/v1/blocklist/dynamic                   → liste les domaines dynamiques
DELETE /api/v1/blocklist/dynamic/{domain}        → supprime un domaine dynamique
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from ....db.mongodb import get_db
from .auth import get_current_user

router = APIRouter(prefix="/blocklist", tags=["blocklist"])

# Clé secrète partagée avec Squid (réseau Docker interne uniquement)
INTERNAL_SECRET = "squid-internal-secret-2024"

CATEGORY_DOMAINS: dict[str, list[str]] = {

    "jeux": [
        # ── Plateformes jeux navigateur ──────────────────────────────────────
        "miniclip.com", "poki.com", "friv.com", "friv2.com", "friv4school.com",
        "crazygames.com", "y8.com", "y9.com", "kizi.com", "agame.com",
        "silvergames.com", "gamesgames.com", "addictinggames.com",
        "coolmathgames.com", "coolmath.com", "coolmath4kids.com",
        "armorgames.com", "kongregate.com", "newgrounds.com", "andkon.com",
        "onlinegames.io", "gamepix.com", "gamaverse.com", "itch.io",
        "gameflare.com", "gamesnacks.com", "gamedistribution.com",
        "htmlgames.com", "html5games.com", "htmlgames.net",
        "funnygames.org", "girlsgogames.com", "games2jolly.com",
        "games2win.com", "pacogames.com", "plonga.com",
        "netgames.io", "playsaurus.com", "flipline.com",
        "nitrome.com", "bgames.com", "gamesofgondor.com",
        "gamesgames.com", "gamekult.com",
        # ── Jeux .io populaires ───────────────────────────────────────────────
        "bloxd.io", "bloxd.net",
        "slither.io", "agar.io", "diep.io", "krunker.io",
        "moomoo.io", "surviv.io", "zombs.io", "zombsroyale.io",
        "paper.io", "paper-io.com", "paperio.com",
        "skribbl.io", "garticphone.com", "gartic.io",
        "lordz.io", "wormate.io", "deeeep.io",
        "tanksio.com", "tanks.io", "wings.io",
        "superhex.io", "powerline.io", "curve.io",
        "splix.io", "narwhale.io", "hexar.io",
        "battlelands.io", "brutes.io", "doblons.io",
        "littlebigsnake.com", "stabfish.io",
        "warbot.io", "evowars.io", "minigiochi.com",
        "1001games.com", "1001games.fr", "1001jeux.fr",
        "lagged.com", "lagged.fr",
        "gamejolt.com", "gamejolt.net",
        "crazy-games.io", "crazygames.io",
        "gogy.com", "gogygames.com",
        "mathplayground.com", "sheppardsoftware.com",
        "twoplayergames.org", "2playergames.io",
        "unblocked-games.com", "unblocked77.com", "unblocked76.com",
        "mills-eagles.com", "unblockedgames.io",
        "classroom6x.com", "classroom-6x.com",
        "tyrone-unblocked.github.io",
        "weebly.com",  # utilisé pour héberger jeux non bloqués
        # ── Jeux PC / Console majeurs ─────────────────────────────────────────
        "roblox.com", "rbxcdn.com", "rbx.com",
        "minecraft.net", "mojang.com", "minecraftforum.net",
        "epicgames.com", "store.epicgames.com", "fortnite.com",
        "origin.com", "ea.com", "easports.com",
        "battle.net", "battlenet.com", "blizzard.com",
        "steampowered.com", "store.steampowered.com",
        "steamcommunity.com", "steamstatic.com", "steamgames.com",
        "gog.com", "ubisoft.com", "ubisoftconnect.com",
        "rockstargames.com", "socialclub.rockstargames.com",
        "2k.com", "activision.com", "callofduty.com", "warzone.com",
        "bethesda.net", "elderscrollsonline.com",
        "runescape.com", "jagex.com", "oldschool.runescape.com",
        "leagueoflegends.com", "riotgames.com", "valorant.com",
        "dota2.com", "worldofwarcraft.com", "wowhead.com",
        "overwatch.com", "hearthstone.com",
        "genshin.hoyoverse.com", "hoyoverse.com", "mihoyo.com",
        "pubg.com", "battlegroundsgame.com",
        "nexon.com", "maplestory.com",
        "gameloft.com", "king.com",
        "supercell.com", "clashroyale.com", "clashofclans.com",
        "brawlstars.com", "hayday.com",
        "zynga.com", "playtika.com",
        # ── Jeux de hasard / Casino ───────────────────────────────────────────
        "pokerstars.com", "888casino.com", "betway.com",
        "casumo.com", "leovegas.com", "videoslots.com",
        "online-casino.com", "pokerhands.com", "fulltiltpoker.com",
        "casino.com", "casinoroom.com", "mrgreen.com",
        "pokerstars.fr", "winamax.fr", "pokerstrategy.com",
        # ── Streaming de jeux ─────────────────────────────────────────────────
        "twitch.tv", "clips.twitch.tv", "m.twitch.tv",
        "gamespot.com", "ign.com", "kotaku.com",
        "gamesplanet.com", "g2a.com", "gamivo.com",
        "cdkeys.com", "instant-gaming.com", "kinguin.net",
        # ── Sites jeux France ─────────────────────────────────────────────────
        "jeux.com", "jeuxjeuxjeux.fr", "jeux-gratuits.com",
        "jeuxenligne.com", "jeu.fr", "jeuxonline.info",
        "jeuxvideo.com", "jvc.com",
        "jeuxflash.fr", "jeux-fille.fr",
        "jouerenligné.com", "jouer.fr",
    ],

    "adulte": [
        "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com",
        "redtube.com", "youporn.com", "tube8.com", "spankbang.com",
        "porntrex.com", "motherless.com", "hclips.com", "analdin.com",
        "eporner.com", "4tube.com", "pornone.com", "drtuber.com",
        "txxx.com", "beeg.com", "alphaporno.com", "iceporn.com",
        "tnaflix.com", "fuq.com",
        "onlyfans.com", "fansly.com", "manyvids.com", "clips4sale.com",
        "chaturbate.com", "livejasmin.com", "bongacams.com",
        "streamate.com", "camsoda.com", "stripchat.com",
        "cam4.com", "myfreecams.com",
        "brazzers.com", "bangbros.com", "realitykings.com",
        "naughtyamerica.com", "digitalplayground.com",
        "sex.com", "rule34.xxx", "e-hentai.org", "nhentai.net",
        "hentaihaven.xxx", "hanime.tv",
    ],

    "violence": [
        "bestgore.com", "goregrish.com", "theync.com",
        "ogrish.com", "rotten.com", "liveleak.com",
        "kaotic.com", "documenting-reality.com",
        "crazyshit.com", "efukt.com",
    ],

    "réseaux sociaux": [
        "facebook.com", "m.facebook.com", "web.facebook.com",
        "instagram.com", "twitter.com", "x.com",
        "tiktok.com", "vm.tiktok.com", "lite.tiktok.com",
        "snapchat.com", "linkedin.com",
        "pinterest.com", "tumblr.com", "reddit.com",
        "discord.com", "discordapp.com", "discord.gg",
        "telegram.org", "t.me", "web.telegram.org",
        "whatsapp.com", "web.whatsapp.com",
        "vk.com", "ok.ru", "odnoklassniki.ru",
        "kick.com", "bereal.com", "yubo.live",
        "badoo.com", "tinder.com", "bumble.com",
    ],

    "streaming vidéo": [
        "youtube.com", "youtu.be", "m.youtube.com",
        "netflix.com", "hulu.com", "disneyplus.com",
        "hbomax.com", "max.com", "primevideo.com",
        "peacocktv.com", "paramountplus.com",
        "dailymotion.com", "vimeo.com",
        "crunchyroll.com", "funimation.com",
        "bilibili.com", "nicovideo.jp",
        "odysee.com", "bitchute.com", "rumble.com",
        "tf1.fr", "france.tv", "m6.fr", "arte.tv",
        "mytf1.fr", "6play.fr",
    ],

    "streaming musique": [
        "spotify.com", "open.spotify.com",
        "deezer.com", "tidal.com",
        "music.youtube.com", "soundcloud.com",
        "pandora.com", "napster.com",
    ],

    "paris sportifs": [
        "bet365.com", "betclic.com", "unibet.com", "winamax.fr",
        "parionssport.fdj.fr", "betway.com", "williamhill.com",
        "ladbrokes.com", "bwin.com", "pokerstars.com",
        "zebet.fr", "netbet.fr", "1xbet.com", "22bet.com",
        "melbet.com", "betwinner.com",
    ],

    "drogues": [
        "erowid.org", "bluelight.org", "shroomery.org",
        "seedsman.com", "herbies.com",
        "leafly.com", "weedmaps.com",
    ],

    "haine": [
        "stormfront.org", "dailystormer.name",
        "vnnforum.com",
    ],

    "piratage": [
        "thepiratebay.org", "1337x.to", "rarbg.to", "nyaa.si",
        "kickasstorrents.cr", "yts.mx", "eztv.re",
        "torrentz2.eu", "limetorrents.info",
        "piratebay.live", "zooqle.com", "torlock.com",
        "fmovies.to", "123movies.so", "putlocker.vip",
        "solarmovie.one", "primewire.li",
    ],

    "messageries": [
        "whatsapp.com", "web.whatsapp.com",
        "telegram.org", "t.me", "web.telegram.org",
        "signal.org", "messenger.com", "m.me",
        "skype.com", "web.skype.com",
        "zoom.us", "meet.google.com",
        "teams.microsoft.com", "discord.com",
        "slack.com", "viber.com", "line.me",
        "wechat.com", "kik.com",
    ],
}


class DynamicDomainAdd(BaseModel):
    domain: str
    category: str
    source: str = "squid_tfidf"
    confidence: float = 1.0


@router.get("/domains/{child_id}/agent")
async def get_domains_for_agent(child_id: str, current_user=Depends(get_current_user)):
    """
    Retourne la liste complète des domaines bloqués pour un enfant.
    Combine la liste statique CATEGORY_DOMAINS + domaines dynamiques MongoDB.
    """
    db = get_db()
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child_id")
    child = await db.children.find_one({"_id": ObjectId(child_id)})
    if not child:
        raise HTTPException(404, "Child not found")

    blocked_cats: list[str] = child.get("blocked_categories", [])

    # Domaines statiques
    static_domains: set[str] = set()
    for cat in blocked_cats:
        cat_key = cat.lower().strip()
        # Correspondance exacte
        if cat_key in CATEGORY_DOMAINS:
            static_domains.update(CATEGORY_DOMAINS[cat_key])
        else:
            # Correspondance partielle (ex: "Jeux vidéo" → "jeux")
            for key in CATEGORY_DOMAINS:
                if key in cat_key or cat_key in key:
                    static_domains.update(CATEGORY_DOMAINS[key])

    # Domaines dynamiques MongoDB
    dynamic_cursor = db.dynamic_blocklist.find({
        "$or": [
            {"category": {"$in": blocked_cats}},
            {"category": {"$in": [c.lower() for c in blocked_cats]}},
            {"global_block": True}
        ]
    })
    dynamic_docs = await dynamic_cursor.to_list(length=10000)
    dynamic_domains = {doc["domain"] for doc in dynamic_docs}

    all_domains = sorted(static_domains | dynamic_domains)

    return {
        "child_id": child_id,
        "child_name": child.get("name", ""),
        "blocked_categories": blocked_cats,
        "domains": all_domains,
        "count": len(all_domains),
        "static_count": len(static_domains),
        "dynamic_count": len(dynamic_domains),
    }


@router.post("/dynamic/add")
async def add_dynamic_domain(payload: DynamicDomainAdd, current_user=Depends(get_current_user)):
    """Squid/TF-IDF (Windows) soumet un nouveau domaine découvert. (JWT requis)"""
    db = get_db()
    domain = payload.domain.lower().strip().lstrip("www.")
    existing = await db.dynamic_blocklist.find_one({"domain": domain})
    if existing:
        if payload.confidence > existing.get("confidence", 0):
            await db.dynamic_blocklist.update_one(
                {"domain": domain},
                {"$set": {"confidence": payload.confidence, "updated_at": datetime.utcnow()}}
            )
        return {"status": "already_exists", "domain": domain}

    await db.dynamic_blocklist.insert_one({
        "domain": domain,
        "category": payload.category.lower(),
        "source": payload.source,
        "confidence": payload.confidence,
        "global_block": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    return {"status": "added", "domain": domain, "category": payload.category}


@router.post("/dynamic/add_internal")
async def add_dynamic_domain_internal(
    payload: DynamicDomainAdd,
    x_internal_secret: str = Header(default="")
):
    """
    Endpoint interne appelé par Squid (squid_https_blocker + squid_redirector).
    Sécurisé par clé secrète partagée — réseau Docker interne uniquement, pas de JWT.
    Quand Squid/TF-IDF découvre un nouveau domaine malveillant sur Windows,
    il l'ajoute ici → Android le bloquera automatiquement à la prochaine sync (toutes les 2 min).
    """
    if x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(403, "Forbidden — clé interne invalide")

    db = get_db()
    domain = payload.domain.lower().strip().lstrip("www.")
    existing = await db.dynamic_blocklist.find_one({"domain": domain})
    if existing:
        if payload.confidence > existing.get("confidence", 0):
            await db.dynamic_blocklist.update_one(
                {"domain": domain},
                {"$set": {"confidence": payload.confidence, "updated_at": datetime.utcnow()}}
            )
        return {"status": "already_exists", "domain": domain}

    await db.dynamic_blocklist.insert_one({
        "domain": domain,
        "category": payload.category.lower(),
        "source": payload.source,
        "confidence": payload.confidence,
        "global_block": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    })
    return {"status": "added", "domain": domain, "category": payload.category}


@router.get("/dynamic")
async def list_dynamic_domains(current_user=Depends(get_current_user)):
    """Liste tous les domaines dynamiques."""
    db = get_db()
    docs = await db.dynamic_blocklist.find().sort("created_at", -1).to_list(length=5000)
    for d in docs:
        d["_id"] = str(d["_id"])
        if "created_at" in d and hasattr(d["created_at"], "isoformat"):
            d["created_at"] = d["created_at"].isoformat()
    return docs


@router.delete("/dynamic/{domain:path}")
async def delete_dynamic_domain(domain: str, current_user=Depends(get_current_user)):
    """Supprime un domaine de la liste dynamique."""
    db = get_db()
    result = await db.dynamic_blocklist.delete_one({"domain": domain.lower()})
    if result.deleted_count == 0:
        raise HTTPException(404, "Domain not found")
    return {"status": "deleted", "domain": domain}


@router.get("/categories")
async def get_available_categories():
    """Retourne les catégories disponibles et le nombre de domaines statiques."""
    return {cat: len(domains) for cat, domains in CATEGORY_DOMAINS.items()}

"""
Blacklist partagée — catégories → domaines (statique + dynamique via Squid/TF-IDF)
GET  /api/v1/blocklist/domains/{child_id}/agent  → liste pour l'agent Android
POST /api/v1/blocklist/dynamic/add               → Squid/Windows ajoute un domaine découvert
GET  /api/v1/blocklist/dynamic                   → liste les domaines dynamiques
DELETE /api/v1/blocklist/dynamic/{domain}        → supprime un domaine dynamique
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

from ....db.mongodb import get_db
from .auth import get_current_user

router = APIRouter(prefix="/blocklist", tags=["blocklist"])

# ─────────────────────────────────────────────────────────────────────────────
# MAPPING CATÉGORIE → DOMAINES (liste statique exhaustive)
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_DOMAINS: dict[str, list[str]] = {

    "jeux": [
        # Plateformes de jeux en ligne
        "miniclip.com", "addictinggames.com", "poki.com", "friv.com",
        "gamesgames.com", "silvergames.com", "crazygames.com", "y8.com",
        "kizi.com", "agame.com", "coolmathgames.com", "armor games.com",
        "armorgames.com", "kongregate.com", "newgrounds.com", "andkon.com",
        "onlinegames.io", "gamepix.com", "gamaverse.com", "itch.io",
        "roblox.com", "minecraft.net", "mojang.com", "epicgames.com",
        "store.epicgames.com", "fortnite.com", "origin.com", "ea.com",
        "battlenet.com", "battle.net", "blizzard.com", "steampowered.com",
        "store.steampowered.com", "steamcommunity.com", "steamstatic.com",
        "gog.com", "ubisoft.com", "ubisoftconnect.com", "rockstargames.com",
        "socialclub.rockstargames.com", "2k.com", "take2games.com",
        "activision.com", "callofduty.com", "warzone.com", "bethesda.net",
        "elderscrollsonline.com", "runescape.com", "jagex.com",
        "leagueoflegends.com", "riotgames.com", "valorant.com",
        "dota2.com", "store.dota2.com", "worldofwarcraft.com",
        "overwatch.com", "diablo.com", "hearthstone.com",
        "starcraft2.com", "starcraft.com", "heroes.blizzard.com",
        "genshin.hoyoverse.com", "hoyoverse.com", "mihoyo.com",
        "genshin-impact.fandom.com", "teyvat.mihoyo.com",
        "pubg.com", "battlegroundsgame.com",
        "nexon.com", "nexonamerica.com", "maplestory.com",
        "gameloft.com", "kingdigital.com", "king.com",
        "candy-crush.com", "supercell.com", "clashroyale.com",
        "clashofclans.com", "brawlstars.com",
        "pocketgems.com", "playtika.com", "zynga.com", "wixgame.com",
        "funnygames.org", "girlsgogames.com", "games2jolly.com",
        "games2win.com", "spele.nl", "spel.nl", "juegosdefriv.com",
        "pacogames.com", "oyunlar1.com", "oyunlar.com",
        "plonga.com", "netgames.io", "playsaurus.com",
        "flipline.com", "papas-games.io", "idletycoon.com",
        "nitro.com", "nitrogames.com", "nitrome.com",
        "gameflare.com", "gamesgames.com", "gamesnacks.com",
        "gamedistribution.com", "htmlgames.com", "html5games.com",
        "jeux.com", "jeuxjeuxjeux.fr", "jeux-gratuits.com",
        "jeuxenligne.com", "jeu.fr", "jeuxonline.info",
        "jeuxvideo.com", "jvc.com", "gamekult.com",
        "gamesofgondor.com", "bgames.com",
        # Jeux de hasard / casino
        "pokerstars.com", "888casino.com", "betway.com", "bet365.com",
        "casumo.com", "leovegas.com", "casinoroom.com", "videoslots.com",
        "williamhill.com", "ladbrokes.com", "draftkings.com", "fanduel.com",
        "online-casino.com", "pokerhands.com", "fulltiltpoker.com",
        # Streaming de jeux
        "twitch.tv", "clips.twitch.tv", "player.twitch.tv",
        "gamespot.com", "ign.com", "kotaku.com",
        "gamesplanet.com", "g2a.com", "gamivo.com", "eneba.com",
        "cdkeys.com", "instant-gaming.com", "kinguin.net",
    ],

    "adulte": [
        "pornhub.com", "xvideos.com", "xnxx.com", "xhamster.com",
        "redtube.com", "youporn.com", "tube8.com", "spankbang.com",
        "porntrex.com", "motherless.com", "hclips.com", "analdin.com",
        "eporner.com", "4tube.com", "pornone.com", "drtuber.com",
        "txxx.com", "shemale.xxx", "tranny.one",
        "beeg.com", "alphaporno.com", "iceporn.com", "tnaflix.com",
        "fapster.xxx", "fuq.com", "fux.com", "vidoza.net",
        "onlyfans.com", "fansly.com", "manyvids.com", "clips4sale.com",
        "chaturbate.com", "livejasmin.com", "bongacams.com", "streamate.com",
        "camsoda.com", "stripchat.com", "jasmin.com", "cam4.com",
        "myfreecams.com", "ifriends.com",
        "brazzers.com", "bangbros.com", "reality kings.com",
        "realitykings.com", "naughtyamerica.com", "digitalplayground.com",
        "babes.com", "devilsfilm.com", "evilangel.com",
        "sex.com", "rule34.xxx", "e-hentai.org", "nhentai.net",
        "hentaihaven.xxx", "hanime.tv",
    ],

    "violence": [
        "bestgore.com", "goregrish.com", "theync.com",
        "ogrish.com", "rotten.com", "liveleak.com",
        "kaotic.com", "watchpeoplediecom.com",
        "documenting-reality.com",
    ],

    "réseaux sociaux": [
        "facebook.com", "m.facebook.com", "web.facebook.com",
        "instagram.com", "twitter.com", "x.com",
        "tiktok.com", "vm.tiktok.com",
        "snapchat.com", "linkedin.com",
        "pinterest.com", "tumblr.com", "reddit.com",
        "discord.com", "discordapp.com", "discord.gg",
        "telegram.org", "t.me", "web.telegram.org",
        "whatsapp.com", "web.whatsapp.com",
        "vk.com", "ok.ru", "odnoklassniki.ru",
        "twitch.tv", "kick.com",
        "bereal.com", "yubo.live", "skout.com",
        "meetme.com", "badoo.com", "tinder.com",
        "bumble.com", "hinge.co",
    ],

    "streaming vidéo": [
        "youtube.com", "youtu.be", "m.youtube.com",
        "netflix.com", "hulu.com", "disneyplus.com",
        "hbomax.com", "max.com", "primevideo.com",
        "peacocktv.com", "paramountplus.com", "appletv.apple.com",
        "dailymotion.com", "vimeo.com", "twitch.tv",
        "crunchyroll.com", "funimation.com", "hidive.com",
        "bilibili.com", "nicovideo.jp", "rutube.ru",
        "odysee.com", "bitchute.com", "rumble.com",
        "ok.ru", "vk.com/video",
        "tf1.fr", "france.tv", "m6.fr", "arte.tv",
        "rmc.fr", "bfmtv.com", "cnews.fr",
        "nrj-play.fr", "rtbf.be", "rts.ch",
        "mytf1.fr", "6play.fr", "salto.fr",
    ],

    "streaming musique": [
        "spotify.com", "open.spotify.com",
        "deezer.com", "tidal.com", "apple.com/music",
        "music.youtube.com", "soundcloud.com",
        "pandora.com", "iheartradio.com",
        "napster.com", "last.fm",
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
        "rollsafe.org", "drugsunlimited.com",
        "seedsman.com", "herbies.com", "cannabis.com",
        "leafly.com", "weedmaps.com",
    ],

    "haine": [
        "stormfront.org", "dailystormer.name", "vnnforum.com",
        "dailyarchive.com", "hate.com",
    ],

    "piratage": [
        "thepiratebay.org", "1337x.to", "rarbg.to", "nyaa.si",
        "kickasstorrents.cr", "yts.mx", "eztv.re",
        "torrentz2.eu", "limetorrents.info", "torrentdownloads.me",
        "piratebay.live", "thepiratebay.rocks",
        "zooqle.com", "torlock.com", "bittorrent.am",
        "extratorrent.unblockit.cam",
        "fmovies.to", "123movies.so", "putlocker.vip",
        "solarmovie.one", "primewire.li",
        "sockshare.ac", "watchfree.ac", "gostream.site",
        "cmovies.cc", "watchseries.ac",
    ],

    "messageries": [
        "whatsapp.com", "web.whatsapp.com",
        "telegram.org", "t.me", "web.telegram.org",
        "signal.org", "messenger.com", "m.me",
        "skype.com", "web.skype.com",
        "zoom.us", "meet.google.com",
        "teams.microsoft.com", "discord.com",
        "slack.com", "hangouts.google.com",
        "viber.com", "line.me", "wechat.com",
        "kik.com", "wickr.com",
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# MODÈLES
# ─────────────────────────────────────────────────────────────────────────────
class DynamicDomainAdd(BaseModel):
    domain: str
    category: str
    source: str = "squid_tfidf"      # qui a soumis ce domaine
    confidence: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/domains/{child_id}/agent")
async def get_domains_for_agent(child_id: str, current_user=Depends(get_current_user)):
    """
    Retourne la liste complète des domaines bloqués pour un enfant.
    Combine :
      - la liste statique CATEGORY_DOMAINS selon blocked_categories du profil
      - les domaines dynamiques ajoutés par Squid/TF-IDF
    """
    db = get_db()

    # Récupérer le profil de l'enfant
    if not ObjectId.is_valid(child_id):
        raise HTTPException(400, "Invalid child_id")
    child = await db.children.find_one({"_id": ObjectId(child_id)})
    if not child:
        raise HTTPException(404, "Child not found")

    blocked_cats: list[str] = child.get("blocked_categories", [])

    # Domaines statiques selon catégories bloquées
    static_domains: set[str] = set()
    for cat in blocked_cats:
        cat_key = cat.lower()
        if cat_key in CATEGORY_DOMAINS:
            static_domains.update(CATEGORY_DOMAINS[cat_key])
        # Chercher correspondance partielle (ex: "Jeux" → "jeux")
        for key in CATEGORY_DOMAINS:
            if key in cat_key or cat_key in key:
                static_domains.update(CATEGORY_DOMAINS[key])

    # Domaines dynamiques depuis MongoDB (découverts par Squid)
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
    """
    Squid/TF-IDF (Windows) soumet un nouveau domaine découvert.
    Il est ajouté à dynamic_blocklist en MongoDB.
    Tous les agents Android le bloqueront au prochain sync.
    """
    db = get_db()
    domain = payload.domain.lower().strip().lstrip("www.")

    # Éviter les doublons
    existing = await db.dynamic_blocklist.find_one({"domain": domain})
    if existing:
        # Mettre à jour la confiance si plus haute
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
    """Liste tous les domaines dynamiques (pour l'interface parent)."""
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
    return {
        cat: len(domains)
        for cat, domains in CATEGORY_DOMAINS.items()
    }

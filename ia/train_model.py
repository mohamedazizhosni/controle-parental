#!/usr/bin/env python3
"""
Script d'entraînement TF-IDF + Naive Bayes
Lancer UNE FOIS pour générer model.pkl et vectorizer.pkl
    python3 train_model.py
"""
import sys
import os
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report

sys.path.insert(0, os.path.dirname(__file__))
try:
    from keywords import KEYWORDS, BLOCKED_DOMAINS
except ImportError:
    print("Erreur: keywords.py introuvable")
    sys.exit(1)

# ── Génération du dataset d'entraînement ─────────────────────────────────────

def build_dataset():
    texts = []
    labels = []

    # Données par catégorie à partir des mots-clés
    category_sentences = {
        "adult": [
            "free porn videos xxx naked girls live sex cam adult content",
            "hot nude women hardcore sex video pornhub xvideos",
            "escort service adult dating erotic massage nude photos",
            "hentai anime xxx cartoon sex adult content 18+",
            "onlyfans nude leaked sex tape naked celebrity",
            "live sex cam girls chaturbate free adult webcam",
            "porn stars videos free hardcore adult movies",
            "xxx amateur homemade sex tape leaked nude",
            "adult site free naked videos sex cam live girls show",
            "milf porn hardcore sex videos adult tube free",
            "teen sex xxx nude photos adult content free",
            "gay porn hardcore adult videos xxx free",
            "lesbian sex videos adult xxx free tube",
            "bdsm bondage fetish sex adult content",
            "strip tease nude adult show live cam free",
            "sexe porno nu gratuit adulte video cam",
            "site adulte gratuit video nu porno",
            "escort girl massage erotique adulte rencontre",
        ],
        "violence": [
            "gore video murder blood death real execution",
            "kill shooting massacre brutal death video",
            "terrorist bomb attack explosion brutal murder",
            "beheading gore real death video blood",
            "torture brutal kill video gore real",
            "cartel murder execution shooting video",
            "real fight brutal street violence blood",
            "war crimes massacre genocide execution video",
            "snuff film real death murder gore video",
            "knife stabbing blood murder brutal attack",
            "gun shooting murder crime blood gore video",
            "death fight blood real brutal kill video",
            "meurtre violence sang mort execution video",
            "attentat bombe terrorisme mort violence",
        ],
        "gambling": [
            "casino online slots jackpot win real money",
            "poker bet sports betting online casino bonus",
            "slot machine jackpot casino bonus free spins",
            "sports betting odds win money online gambling",
            "blackjack roulette casino play real money win",
            "online poker tournament win cash prize",
            "casino welcome bonus free spins no deposit",
            "bet365 betway poker casino gambling online",
            "paris sportifs casino en ligne pari argent",
            "roulette poker machine sous casino gratuit",
            "crypto casino bitcoin gambling win jackpot",
            "lottery win jackpot gambling bet money online",
        ],
        "social": [
            "facebook instagram social network friends share",
            "tiktok viral video social media followers",
            "youtube video subscribe channel social media",
            "twitter tweet social network trending hashtag",
            "snapchat stories friends chat social network",
            "discord server chat gaming community social",
            "reddit forum community social post upvote",
            "whatsapp telegram chat message social",
            "instagram followers likes photos social network",
            "twitch live stream gaming social platform",
            "omegle chat strangers video social",
            "tinder dating app social match swipe",
        ],
        "games": [
            "minecraft fortnite roblox free online game play",
            "steam gaming online multiplayer fps game",
            "call of duty warzone fps shooter game online",
            "league of legends valorant online game free",
            "free fire pubg battle royale online game",
            "gta grand theft auto game online free play",
            "gaming fps rpg mmorpg online multiplayer",
            "game download free play online browser",
            "playstation xbox nintendo gaming console",
            "esport tournament gaming online competitive",
            "roblox minecraft free game kids online play",
            "epic games fortnite free download game",
        ],
        "safe": [
            "weather forecast temperature today sunny rain",
            "news article politics economy international",
            "recipe cooking food ingredients delicious",
            "school homework math history science lesson",
            "sports football basketball player team score",
            "music album artist song lyrics radio",
            "travel destination hotel booking tourism",
            "technology software development programming",
            "health medical doctor hospital medicine",
            "science research university study education",
            "math cours education apprendre école",
            "actualité journal politique économie france",
            "météo prévision température pluie soleil",
            "cuisine recette ingrédients repas délicieux",
            "sport football basketball équipe joueur",
            "wikipedia encyclopedia knowledge article",
            "online shopping product buy price review",
            "bank account finance money transfer secure",
            "government official public service citizen",
            "news blog article read information latest",
            "tutorial learn programming python web dev",
            "dictionary definition meaning word language",
        ],
    }

    # Générer des exemples depuis les domaines bloqués
    for cat, domains in BLOCKED_DOMAINS.items():
        for domain in domains[:30]:
            domain_text = domain.replace(".", " ").replace("-", " ")
            texts.append(f"{domain_text} {domain_text} adult content site")
            labels.append(cat)

    # Générer des exemples depuis les mots-clés
    for cat, words in KEYWORDS.items():
        # Combiner les mots par groupes de 5
        for i in range(0, len(words), 5):
            group = words[i:i+5]
            texts.append(" ".join(group) + " " + " ".join(group))
            labels.append(cat)

    # Ajouter les phrases pré-construites
    for cat, sentences in category_sentences.items():
        for sentence in sentences:
            texts.append(sentence)
            labels.append(cat)
            # Duplication avec variation pour enrichir
            texts.append(sentence + " free online site web")
            labels.append(cat)

    return texts, labels


def train():
    print("Construction du dataset...")
    texts, labels = build_dataset()

    print(f"Dataset : {len(texts)} exemples")
    from collections import Counter
    print("Distribution:", Counter(labels))

    X_train, X_test, y_train, y_test = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=labels
    )

    print("Entraînement TF-IDF + Naive Bayes...")
    pipeline = Pipeline([
        ('tfidf', TfidfVectorizer(
            ngram_range=(1, 3),       # unigrammes, bigrammes, trigrammes
            max_features=50000,
            min_df=1,
            sublinear_tf=True,
            analyzer='word',
            token_pattern=r'\b[a-zA-Z0-9]+\b',
        )),
        ('clf', MultinomialNB(alpha=0.1)),
    ])

    pipeline.fit(X_train, y_train)

    print("\nÉvaluation sur le jeu de test :")
    y_pred = pipeline.predict(X_test)
    print(classification_report(y_test, y_pred))

    # Sauvegarde
    model_path = os.path.join(os.path.dirname(__file__), "model.pkl")
    joblib.dump(pipeline, model_path)
    print(f"\nModèle sauvegardé : {model_path}")

    # Test rapide
    tests = [
        "free porn xxx naked girls adult sex cam",
        "gore murder blood death execution video",
        "casino slots win jackpot real money bet",
        "minecraft fortnite game online free play",
        "weather news recipe cooking school homework",
        "adult site nude video sex cam live show",
        "nouveau site adulte gratuit video xxx",
        "violence gore blood murder brutal video",
    ]
    print("\nTests rapides :")
    for t in tests:
        pred = pipeline.predict([t])[0]
        proba = pipeline.predict_proba([t])[0]
        conf = max(proba)
        print(f"  [{pred:10s} {conf:.2f}] {t[:50]}")


if __name__ == "__main__":
    train()

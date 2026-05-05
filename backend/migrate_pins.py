"""
Script de migration des PINs en clair vers PINs hachés avec bcrypt

Usage:
    python migrate_pins.py

Attention: Exécuter une seule fois après le déploiement des nouvelles modifications
"""

import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext

# Configuration - Lire depuis les variables d'environnement
MONGO_URL = os.getenv("MONGO_URL", "mongodb://mongodb:27017")
DATABASE_NAME = "parental_db"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def migrate_pins():
    """Migrer tous les PINs en clair vers format haché."""
    print("🔄 Connexion à MongoDB...")
    print(f"   URL: {MONGO_URL}")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DATABASE_NAME]
    
    try:
        # Récupérer tous les profils enfants
        children = await db.children.find({}).to_list(None)
        total = len(children)
        
        if total == 0:
            print("ℹ️  Aucun profil enfant trouvé.")
            return
        
        print(f"📊 {total} profil(s) enfant(s) trouvé(s).\n")
        
        migrated_count = 0
        skipped_count = 0
        
        for child in children:
            child_name = child.get("name", "Inconnu")
            updates = {}
            
            # Vérifier le PIN parent
            parent_pin = child.get("parent_pin")
            if parent_pin:
                # Si le PIN commence par $2b$, c'est déjà un hash bcrypt
                if parent_pin.startswith("$2b$"):
                    print(f"⏭️  {child_name} - PIN parent déjà haché")
                else:
                    # Hacher le PIN en clair
                    updates["parent_pin"] = pwd_context.hash(parent_pin)
                    print(f"🔐 {child_name} - PIN parent haché: {parent_pin[:4]}****")
            
            # Vérifier le PIN enfant
            child_pin = child.get("child_pin")
            if child_pin:
                if child_pin.startswith("$2b$"):
                    print(f"⏭️  {child_name} - PIN enfant déjà haché")
                else:
                    updates["child_pin"] = pwd_context.hash(child_pin)
                    print(f"🔐 {child_name} - PIN enfant haché: {child_pin[:4]}****")
            
            # Appliquer les mises à jour si nécessaire
            if updates:
                await db.children.update_one(
                    {"_id": child["_id"]}, 
                    {"$set": updates}
                )
                migrated_count += 1
                print(f"✅ {child_name} - Migré avec succès\n")
            else:
                skipped_count += 1
                print(f"⏭️  {child_name} - Aucune migration nécessaire\n")
        
        print("\n" + "="*50)
        print(f"✅ Migration terminée !")
        print(f"   - {migrated_count} profil(s) migré(s)")
        print(f"   - {skipped_count} profil(s) ignoré(s) (déjà migrés)")
        print("="*50)
        
    except Exception as e:
        print(f"❌ Erreur lors de la migration : {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        client.close()


async def verify_migration():
    """Vérifier que tous les PINs sont bien hachés."""
    print("\n🔍 Vérification de la migration...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DATABASE_NAME]
    
    try:
        children = await db.children.find({}).to_list(None)
        
        all_good = True
        for child in children:
            name = child.get("name", "Inconnu")
            parent_pin = child.get("parent_pin")
            child_pin = child.get("child_pin")
            
            if parent_pin and not parent_pin.startswith("$2b$"):
                print(f"⚠️  {name} - PIN parent non haché : {parent_pin}")
                all_good = False
            
            if child_pin and not child_pin.startswith("$2b$"):
                print(f"⚠️  {name} - PIN enfant non haché : {child_pin}")
                all_good = False
        
        if all_good:
            print("✅ Tous les PINs sont correctement hachés !")
        else:
            print("⚠️  Certains PINs ne sont pas hachés. Relancez la migration.")
        
    finally:
        client.close()


if __name__ == "__main__":
    print("="*50)
    print("🔐 Migration des PINs - Contrôle Parental")
    print("="*50)
    print()
    
    # Demander confirmation
    response = input("⚠️  Cette opération va modifier tous les PINs en base de données.\nContinuer ? (oui/non) : ")
    
    if response.lower() not in ["oui", "yes", "y", "o"]:
        print("❌ Migration annulée.")
        sys.exit(0)
    
    print()
    
    # Exécuter la migration
    asyncio.run(migrate_pins())
    
    # Vérifier le résultat
    asyncio.run(verify_migration())

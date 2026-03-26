import os
import pandas as pd

# Vérifie que ce chemin est toujours correct pour toi
BASE_PATH = r"D:\TRADING\ENTREPRISE\0 - Phase de lancement\Stratégie de trading\0 - Backtest\Data"


def load_data(asset: str, timeframe: str = "1m", mode: str = "ohlcv"):
    """
    Charge et concatène TOUS les fichiers CSV d'un dossier d'actif.
    """

    folder_name = f"{asset} {timeframe}"
    folder_path = os.path.join(BASE_PATH, folder_name)

    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"Le dossier n'existe pas : {folder_path}")

    # Récupérer tous les CSV
    csv_files = [f for f in os.listdir(folder_path) if f.endswith(".csv")]
    if len(csv_files) == 0:
        raise FileNotFoundError(f"Aucun CSV trouvé dans : {folder_path}")

    # Tri pour charger dans l'ordre chronologique (important)
    csv_files.sort()
    
    all_dfs = []
    print(f"📂 Chargement de {len(csv_files)} fichiers pour {asset}...")

    for file in csv_files:
        file_path = os.path.join(folder_path, file)
        try:
            # Lecture du chunk
            df_chunk = pd.read_csv(file_path)
            all_dfs.append(df_chunk)
        except Exception as e:
            print(f"⚠️ Erreur lecture {file}: {e}")

    # Fusion de tous les morceaux
    if not all_dfs:
        raise Exception("Aucune donnée n'a pu être chargée.")
        
    df = pd.concat(all_dfs, ignore_index=True)

    # --- NETTOYAGE & FORMATAGE ---
    
    # Normalisation des colonnes
    df.columns = [c.lower() for c in df.columns]

    required_cols = ["timestamp", "open", "high", "low", "close", "volume"]
    for col in required_cols:
        if col not in df.columns:
            # Tentative de gestion d'erreur si le format change
            raise Exception(f"Colonne manquante '{col}' dans les CSV de {asset}")

    # Convertir timestamp -> index datetime
    # utc=True est crucial pour éviter les erreurs de timezone mixtes lors de la concat
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")

    # Trier par date (Sécurité post-concaténation)
    df = df.sort_index()

    # Gestion des doublons (Si des fichiers se chevauchent)
    df = df[~df.index.duplicated(keep='first')]

    # Nettoyage minimal
    df = df.dropna()

    if mode == "close":
        return df["close"]

    return df[["open", "high", "low", "close", "volume"]]
"""PARADIGMA IMPERATIVO: entrenamiento e inferencia paso a paso.

Conserva las cinco variables, el split y los hiperparámetros ganadores
registrados en MODELO PERFUMES PROT.ipynb. sklearn usa objetos internamente;
la lógica de esta funcionalidad es procedural, con secuencias, bucles y estado.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from .functional import clp_to_usd, priced_perfume
from .schema import CLIMATES, FEATURES, GENDERS, OCCASIONS, PRICE, TARGET

DEFAULT_MODEL = Path(__file__).parent / "artifacts" / "perfumes.joblib"


def read_dataset(csv_path):
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    missing = set((*FEATURES, TARGET, PRICE)) - set(df.columns)
    if missing:
        raise ValueError("Faltan columnas: " + ", ".join(sorted(missing)))
    df = df.loc[:, [*FEATURES, TARGET, PRICE]].copy()
    if df.isna().any().any():
        raise ValueError("El dataset contiene valores vacíos en columnas requeridas.")
    for column in (*FEATURES, PRICE):
        df[column] = pd.to_numeric(df[column], errors="raise")
        if not np.isfinite(df[column]).all():
            raise ValueError(f"{column} contiene valores no finitos.")
    for column, valid in (("Clima_Cod", CLIMATES.values()),
                          ("Ocasion_Cod", OCCASIONS.values()),
                          ("Genero_Cod", GENDERS.values())):
        if not df[column].isin(valid).all():
            raise ValueError(f"Codificación inválida en {column}; revisa el notebook.")
    if not df["Edad"].between(1, 120).all() or not (df["Edad"] % 1 == 0).all():
        raise ValueError("Edad debe contener enteros entre 1 y 120.")
    if (df[["Presupuesto_USD", PRICE]] <= 0).any().any():
        raise ValueError("Los precios y presupuestos deben ser positivos.")
    if not df[TARGET].map(lambda value: isinstance(value, str) and bool(value.strip())).all():
        raise ValueError("Cada perfume debe tener un nombre de texto no vacío.")
    df[TARGET] = df[TARGET].str.strip()
    # Un duplicado exacto no debe aparecer a ambos lados del conjunto de evaluación.
    duplicates = int(df.duplicated().sum())
    df = df.drop_duplicates().reset_index(drop=True)
    counts = df[TARGET].value_counts()
    if len(counts) < 2 or counts.min() < 5:
        raise ValueError("Se necesitan al menos 2 perfumes y 5 filas distintas por perfume para el split 80/20.")
    return df, duplicates


def train(csv_path, output=DEFAULT_MODEL):
    csv_path, output = Path(csv_path), Path(output)
    df, removed_duplicates = read_dataset(csv_path)
    x_train, x_test, y_train, y_test = train_test_split(
        df[list(FEATURES)], df[TARGET], test_size=0.2, random_state=42, stratify=df[TARGET],
    )
    model = RandomForestClassifier(
        n_estimators=300, max_depth=12, min_samples_split=4, random_state=42, n_jobs=2,
    )
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)
    top3_hits = 0
    for index, real in enumerate(y_test):
        best = np.argsort(-probabilities[index], kind="stable")[:3]
        if real in model.classes_[best]:
            top3_hits += 1
    catalog = []
    for name, records in df.groupby(TARGET, sort=True):
        catalog.append({
            "name": name,
            "price_usd": float(records[PRICE].median()),
            "availability": "not_verified",
        })
    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "f1_weighted": float(f1_score(y_test, predictions, average="weighted", zero_division=0)),
        "top3_accuracy": top3_hits / len(y_test),
        "train_rows": len(x_train), "test_rows": len(x_test),
        "classes": len(model.classes_), "duplicates_removed": removed_duplicates,
    }
    bundle = {
        "schema_version": 1, "sklearn_version": sklearn.__version__,
        "features": list(FEATURES), "model": model, "catalog": catalog,
        "metrics": metrics, "dataset_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "price_source": "Mediana de Precio_Real_USD por perfume en el dataset; precio referencial.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publicar todo junto evita mezclar modelo y precios de distintas versiones.
    with NamedTemporaryFile(dir=output.parent, suffix=".joblib", delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        joblib.dump(bundle, temporary, compress=3)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return metrics


def load_bundle(path):
    # Solo artefactos locales generados por el comando train, nunca pickles subidos por HTTP.
    bundle = joblib.load(path)
    if bundle.get("schema_version") != 1 or bundle.get("features") != list(FEATURES):
        raise ValueError("El artefacto no corresponde al esquema del recomendador.")
    if bundle.get("sklearn_version") != sklearn.__version__:
        raise ValueError("Versión de scikit-learn distinta: vuelve a entrenar con requirements.txt.")
    names = {perfume["name"] for perfume in bundle["catalog"]}
    if names != set(bundle["model"].classes_):
        raise ValueError("El catálogo de precios no coincide con las clases del modelo.")
    return bundle


def recommend(bundle, age, climate, occasion, budget_clp, gender, rate, top_n=3):
    if not 1 <= age <= 120 or not 1 <= top_n <= 10:
        raise ValueError("Edad o cantidad de recomendaciones inválida.")
    profile = pd.DataFrame([{
        "Edad": age, "Clima_Cod": CLIMATES[climate], "Ocasion_Cod": OCCASIONS[occasion],
        "Presupuesto_USD": clp_to_usd(budget_clp, rate), "Genero_Cod": GENDERS[gender],
    }], columns=list(FEATURES))
    probabilities = bundle["model"].predict_proba(profile)[0]
    indexes = np.argsort(-probabilities, kind="stable")[:top_n]
    prices = {}
    for perfume in bundle["catalog"]:
        prices[perfume["name"]] = perfume
    recommendations = []
    for index in indexes:
        name = bundle["model"].classes_[index]
        item = priced_perfume(prices[name], rate)
        item["score_percent"] = round(float(probabilities[index]) * 100, 2)
        item["within_budget"] = item["price_clp"] <= budget_clp
        recommendations.append(item)
    return recommendations


def main():
    parser = argparse.ArgumentParser(description="Entrena el Random Forest del notebook con el CSV original.")
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()
    try:
        metrics = train(args.csv, args.output)
    except (ValueError, OSError) as error:
        parser.exit(1, f"No se pudo entrenar: {error}\n")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

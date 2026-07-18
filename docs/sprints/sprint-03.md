# Sprint 3 — Modèles dbt incrémentaux

## Objectif

Séparer le référentiel courant des stations de l’historique de leur
disponibilité et éviter la reconstruction complète de la table de faits.

## Grain des modèles

### `dim_stations`

Une ligne représente une station Vélib dans son état descriptif le plus
récemment ingéré.

Clé unique :

```text
station_id
```

La dimension contient notamment :

- le nom courant ;
- la capacité courante ;
- la commune ;
- le code INSEE ;
- les coordonnées ;
- la première date d’ingestion connue ;
- la dernière date d’ingestion connue ;
- la dernière date métier publiée par la source.

### `fct_velib_status`

Une ligne représente l’état d’une station à un horodatage métier donné.

Clé unique :

```text
observation_id
```

La clé est calculée de manière déterministe à partir de :

```text
station_id + status_updated_at
```

## Stratégie incrémentale

Le modèle utilise :

```text
materialized=incremental
incremental_strategy=delete+insert
unique_key=observation_id
```

Seules les lignes dont `loaded_at` est supérieur au dernier chargement
présent dans la table de faits sont sélectionnées.

## Validation incrémentale

État initial :

```text
raw_rows=2027
fact_rows=2027
```

Après une nouvelle ingestion :

```text
RAW inserted=1501
FACT inserted=1501
```

Relance dbt sans nouvelle ingestion :

```text
FACT inserted=0
```

Cela confirme que le modèle est incrémental et idempotent.

## Dimension courante et historique

La station `8028` a eu deux capacités déclarées :

```text
ancienne capacité=1
capacité courante=52
```

`dim_stations` expose la capacité courante de 52.

`fct_velib_status` conserve les quatre observations historiques et leurs
capacités d’origine, comprises entre 1 et 52.

## Qualité des données

Les tests bloquants couvrent :

- unicité des stations ;
- unicité des observations ;
- relation entre les faits et la dimension ;
- valeurs obligatoires ;
- valeurs négatives ;
- cohérence vélos mécaniques + électriques ;
- validité des coordonnées ;
- valeurs acceptées des statuts ;
- clés métier de la source RAW.

Le contrôle vélos disponibles/capacité reste un avertissement, car l’API
publie parfois une valeur légèrement supérieure à la capacité déclarée.

Les anomalies sont conservées dans le schéma d’audit dbt.

## Fraîcheur

La source RAW est contrôlée avec les seuils suivants :

- avertissement après 2 heures ;
- erreur après 6 heures.

Le DAG exécute :

```bash
dbt source freshness --profiles-dir .
```

avant les modèles et les tests.

## Résultats

```text
Models: PASS=3 ERROR=0
Tests: PASS=24 WARN=1 ERROR=0
Source freshness: PASS
Python tests: 7 passed
Airflow import errors: none
```

## Limites connues à la fin du sprint

- `dim_stations` est une dimension courante, pas une SCD Type 2 ;
- les métriques techniques des ingestions ne sont pas encore historisées ;
- aucune politique de rétention des faits n’est encore définie ;
- les dashboards Superset doivent être actualisés après stabilisation
  des modèles.
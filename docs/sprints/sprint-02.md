# Sprint 2 — Image Airflow et exécution dbt reproductible

## Objectif

Installer dbt une seule fois lors de la construction de l’image Airflow,
au lieu de le télécharger pendant chaque exécution du DAG.

## Image personnalisée

L’image est construite à partir de :

```text
apache/airflow:2.9.1-python3.11
```

Elle contient :

- Apache Airflow 2.9.1 ;
- Python 3.11 ;
- Git ;
- dbt-core 1.7.19 ;
- dbt-postgres 1.7.19.

## Compatibilité des dépendances

dbt-core 1.9.1 nécessite une version de `protobuf` incompatible avec les
contraintes utilisées par Airflow 2.9.1.

La série dbt 1.7 a donc été retenue afin de préserver un environnement
stable et reproductible.

Les versions sont verrouillées dans :

```text
requirements-airflow.txt
```

## Construction

Commande :

```bash
docker compose build airflow-scheduler
```

Image produite :

```text
mobility-airflow:2.9.1-dbt1.7.19
```

## Contexte de construction

Le fichier `.dockerignore` exclut notamment :

- les données PostgreSQL ;
- les secrets locaux ;
- l’environnement virtuel Python ;
- les logs Airflow ;
- les artefacts dbt ;
- les fichiers Git.

Cela réduit la taille du contexte envoyé à Docker et évite d’intégrer des
fichiers sensibles ou inutiles dans l’image.

## Sécurité du conteneur

Les services Airflow utilisent l’utilisateur défini par `AIRFLOW_UID`
au lieu de s’exécuter avec l’utilisateur root.

Le groupe root reste utilisé conformément au fonctionnement de l’image
officielle Airflow pour la gestion des permissions sur les volumes.

Exemple observé localement :

```text
uid=501(default) gid=0(root) groups=0(root)
```

Le processus n’utilise donc plus `uid=0`.

## Exécution dbt

La tâche Airflow n’installe plus dbt avec `pip`.

Elle exécute directement :

```bash
dbt run --profiles-dir .
dbt test --profiles-dir .
```

## Adaptation à l’historisation

La table `fct_velib_status` contient plusieurs observations par station.

Le test d’unicité sur `station_id` a donc été remplacé par une clé
déterministe `observation_id`, construite à partir de :

```text
station_id + status_updated_at
```

## Qualité des données

L’API Vélib peut publier un nombre de vélos légèrement supérieur à la
capacité déclarée.

Ces observations :

- ne sont pas corrigées artificiellement ;
- ne bloquent pas le pipeline ;
- génèrent un avertissement dbt ;
- sont enregistrées dans le schéma d’audit dbt.

## Résultats

Versions :

```text
Airflow: 2.9.1
dbt-core: 1.7.19
dbt-postgres: 1.7.19
```

Construction dbt :

```text
PASS=2 WARN=0 ERROR=0
```

Tests dbt :

```text
PASS=8 WARN=1 ERROR=0
```

L’avertissement correspond à quatre anomalies réelles de capacité
observées au moment du test.

## Commandes de validation

```bash
docker compose config --quiet
docker compose build airflow-scheduler
docker compose run --rm airflow-scheduler dbt --version
docker compose run --rm airflow-scheduler airflow dags list-import-errors
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

## Limites connues à la fin du sprint

- la table de faits dbt est encore reconstruite entièrement ;
- le référentiel courant des stations n’est pas encore séparé ;
- les métriques d’ingestion ne sont pas encore historisées ;
- la clé Fernet Airflow reste à configurer.
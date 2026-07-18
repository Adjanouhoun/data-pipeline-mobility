# Sprint 13 — Finalisation locale du projet

## Objectif

Finaliser la plateforme locale avant son déploiement sur la VM OVH.

Ce sprint couvre :

- la documentation générale ;
- l’inventaire des composants ;
- la validation complète des tests ;
- l’audit des secrets ;
- la vérification des exports Superset ;
- la validation d’une sauvegarde finale ;
- l’ajout d’une intégration continue ;
- la reproductibilité des images Docker.

## Branche

```text
chore/project-finalization
```

## Documentation générale

Un fichier `README.md` a été ajouté à la racine du dépôt.

Il documente :

- l’objectif du projet ;
- l’architecture ;
- les technologies ;
- les sources Open Data Paris ;
- les DAG Airflow ;
- les schémas PostgreSQL ;
- les modèles dbt ;
- les dashboards Superset ;
- les prérequis ;
- l’installation locale ;
- l’initialisation d’Airflow et Superset ;
- les tests Python ;
- les commandes dbt ;
- les sauvegardes ;
- la restauration ;
- la rétention ;
- les protections de sécurité ;
- les interfaces locales.

## Variables d’environnement

La variable suivante a été ajoutée à `.env.example` :

```dotenv
AIRFLOW_UID=50000
```

Elle permet aux conteneurs Airflow d’écrire les fichiers locaux avec un utilisateur contrôlé.

Sur macOS et Linux, la valeur peut être remplacée par le résultat de :

```bash
id -u
```

Toutes les variables attendues par Docker Compose sont maintenant documentées dans `.env.example`.

## Audit des fichiers versionnés

Les fichiers générés suivants ont été contrôlés :

- `__pycache__` ;
- fichiers `.pyc` ;
- `dbt_mobility/target` ;
- logs dbt ;
- `.env`.

Aucun de ces fichiers n’est versionné.

Les sauvegardes PostgreSQL sont également exclues du dépôt par `.gitignore`.

## Audit des secrets

La recherche a porté notamment sur :

- les anciens mots de passe locaux ;
- les clés secrètes Superset ;
- les mots de passe PostgreSQL ;
- les jetons ;
- les clés d’API ;
- les valeurs d’exemple historiques.

Aucun secret réel n’a été trouvé dans les fichiers versionnés.

Les trois exports Superset contiennent uniquement une URI masquée :

```text
postgresql+psycopg2://data_engineer:XXXXXXXXXX@postgres_destination:5432/mobility_warehouse
```

## Dashboards versionnés

Les dashboards suivants sont présents :

```text
Monitoring de la plateforme
Disponibilité Vélib
Trafic routier parisien
```

Leurs exports sont stockés dans :

```text
superset/exports/monitoring_platform
superset/exports/velib_availability
superset/exports/road_traffic
```

## Intégration continue

Le workflow suivant a été ajouté :

```text
.github/workflows/ci.yml
```

Il est exécuté sur :

- les pull requests ;
- les push vers `main`.

La CI effectue :

1. l’installation de Python 3.11 ;
2. l’installation des dépendances de développement ;
3. l’exécution des tests unitaires ;
4. la compilation des bibliothèques d’ingestion ;
5. la validation syntaxique des scripts shell ;
6. la préparation d’un `.env` depuis `.env.example` ;
7. la validation de Docker Compose.

La syntaxe YAML du workflow a été validée localement.

## Tests Python

Résultat :

```text
Ran 36 tests
OK
```

Les tests couvrent notamment :

- l’API Vélib ;
- la pagination ;
- la déduplication ;
- l’API de trafic routier ;
- la transformation des observations ;
- les upserts routiers ;
- les métriques d’ingestion.

## Scripts opérationnels

Les scripts suivants ont été validés avec `bash -n` :

```text
scripts/backup_warehouse.sh
scripts/verify_warehouse_backup.sh
scripts/apply_data_retention.sh
```

Aucune erreur syntaxique n’a été détectée.

## Docker Compose

La configuration complète a été validée avec :

```bash
docker compose config --quiet
```

Résultat :

```text
configuration valide
```

## Images reproductibles

L’image pgAdmin utilisait auparavant le tag mutable :

```text
dpage/pgadmin4:latest
```

La version active a été identifiée :

```text
9.10
```

Docker Compose utilise désormais :

```text
dpage/pgadmin4:9.10
```

Les autres images principales sont également fixées :

```text
postgres:15-alpine
apache/superset:4.0.1
apache/airflow:2.9.1-python3.11
dbt-core:1.7.19
dbt-postgres:1.7.19
```

## Validation Airflow

La commande suivante ne retourne aucune erreur d’import :

```bash
docker compose run --rm airflow-scheduler \
  airflow dags list-import-errors
```

Résultat :

```text
No data found
```

Les deux DAG sont reconnus :

```text
ingest_and_transform_velib
ingest_paris_road_traffic
```

## Validation dbt

Tous les modèles ont été construits avant l’exécution de la suite complète de tests.

Résultat :

```text
PASS=193
WARN=1
ERROR=0
SKIP=0
TOTAL=194
```

L’unique avertissement concerne :

```text
assert_bikes_available_under_total_capacity
```

Onze observations déclarent davantage de vélos disponibles que la capacité annoncée.

Le test reste volontairement configuré en avertissement, car ces valeurs proviennent de l’API source et ne doivent pas bloquer l’ensemble du pipeline.

## Sauvegarde finale

Une sauvegarde finale a été créée :

```text
mobility_warehouse_20260718T170550Z.dump
```

La somme SHA-256 a été validée.

L’archive PostgreSQL a été restaurée dans une base temporaire.

## Volumes Vélib restaurés

```text
velib_raw_rows=6536
velib_fact_rows=6535
velib_station_rows=1516
velib_daily_rows=3225
velib_monitoring_rows=4
```

## Volumes trafic restaurés

```text
traffic_raw_rows=8937
traffic_fact_rows=8937
traffic_arc_rows=2979
traffic_daily_rows=2979
traffic_monitoring_rows=5
```

Les contrôles de cohérence après restauration ont réussi.

Un marqueur `.verified` a été créé pour l’archive.

La base temporaire de vérification a ensuite été supprimée.

## État des services

Les services permanents suivants ont été démarrés et vérifiés :

```text
postgres_metadata
postgres_destination
postgres_superset
airflow-webserver
airflow-scheduler
superset
pgadmin
```

Les bases PostgreSQL et Superset sont déclarées saines.

Les interfaces locales sont disponibles sur :

```text
Airflow:  http://localhost:8085
Superset: http://localhost:8088
pgAdmin:  http://localhost:8051
Warehouse PostgreSQL: localhost:5435
```

## Résultat

La plateforme locale est documentée, testée, sauvegardée et reproductible.

Elle comprend :

- deux pipelines Airflow ;
- deux sources Open Data Paris ;
- un entrepôt PostgreSQL historisé ;
- des modèles dbt incrémentaux ;
- 194 contrôles dbt ;
- 36 tests Python ;
- trois dashboards Superset ;
- une procédure de sauvegarde et restauration ;
- une politique de rétention protégée ;
- une intégration continue GitHub Actions.

## Suite

Le Sprint 14 sera consacré au déploiement sur la VM OVH :

- configuration de production ;
- séparation des réseaux et volumes ;
- création des secrets ;
- restauration de l’entrepôt ;
- import des dashboards ;
- exposition HTTPS ;
- planification des sauvegardes ;
- validation de production.
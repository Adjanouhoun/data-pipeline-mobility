# Data Pipeline Mobility

Plateforme locale de données consacrée à la mobilité parisienne.

Le projet collecte les données Vélib et les comptages routiers permanents de Paris, les historise dans PostgreSQL, les transforme avec dbt, les orchestre avec Apache Airflow et les expose dans des dashboards Apache Superset.

## Fonctionnalités

- ingestion complète et idempotente des stations Vélib ;
- ingestion incrémentale du trafic routier parisien ;
- pagination, reprises HTTP et validation des réponses API ;
- stockage brut historisé dans PostgreSQL ;
- modèles dbt incrémentaux ;
- dimensions, tables de faits et agrégats quotidiens ;
- contrôles de qualité et tests métier ;
- monitoring des exécutions Airflow ;
- dashboards Superset versionnés ;
- sauvegarde et restauration vérifiée de l’entrepôt ;
- politique de rétention protégée ;
- index PostgreSQL adaptés aux requêtes analytiques.

## Architecture

```mermaid
flowchart LR
    API1["API Vélib Paris"] --> AF["Apache Airflow"]
    API2["API trafic routier Paris"] --> AF

    AF --> RAW["PostgreSQL\nschema_raw"]
    AF --> MON["PostgreSQL\nschema_monitoring"]

    RAW --> DBT["dbt"]
    MON --> DBT

    DBT --> ANA["PostgreSQL\nschema_analytics"]
    ANA --> SUP["Apache Superset"]

    SUP --> D1["Monitoring de la plateforme"]
    SUP --> D2["Disponibilité Vélib"]
    SUP --> D3["Trafic routier parisien"]
```

## Technologies

- Python 3.11
- Apache Airflow 2.9.1
- dbt Core 1.7.19
- dbt PostgreSQL 1.7.19
- PostgreSQL 15
- Apache Superset 4.0.1
- Docker Compose
- pgAdmin
- unittest

## Sources de données

### Vélib

Dataset Open Data Paris :

```text
velib-disponibilite-en-temps-reel
```

Le pipeline récupère l’ensemble des stations disponibles avec pagination stable par `stationcode`.

### Trafic routier

Dataset Open Data Paris :

```text
comptages-routiers-permanents
```

Le pipeline utilise une fenêtre temporelle incrémentale avec recouvrement afin de récupérer les nouvelles observations et de corriger les données déjà reçues lorsqu’elles évoluent.

## Pipelines Airflow

### Vélib

DAG :

```text
ingest_and_transform_velib
```

Planification :

```text
@hourly
```

Le DAG :

1. initialise le schéma RAW ;
2. initialise le schéma de monitoring ;
3. récupère toutes les stations Vélib ;
4. insère les observations de manière idempotente ;
5. enregistre les métriques d’ingestion ;
6. exécute les modèles dbt Vélib ;
7. exécute les tests associés.

### Trafic routier

DAG :

```text
ingest_paris_road_traffic
```

Planification :

```text
35 * * * *
```

Le DAG :

1. initialise les tables routières ;
2. initialise le monitoring routier ;
3. détermine la fenêtre d’extraction ;
4. récupère les observations API par segments ;
5. classe les lignes insérées, mises à jour ou inchangées ;
6. enregistre les métriques techniques ;
7. construit et teste les modèles dbt routiers.

La fraîcheur des sources est disponible comme contrôle de diagnostic, mais ne bloque pas une ingestion techniquement réussie lorsque l’API ne publie pas de nouvelle observation.

## Organisation des données

### `schema_raw`

Données historisées telles qu’elles sont reçues et normalisées par Airflow :

- `stg_raw_stations`
- `road_traffic_observations`

### `schema_monitoring`

Métriques techniques des pipelines :

- `ingestion_runs`
- `traffic_ingestion_runs`

### `schema_analytics`

Modèles dbt destinés aux analyses et à Superset :

#### Vélib

- `stg_velib_stations`
- `dim_stations`
- `fct_velib_status`
- `fct_velib_current_status`
- `agg_velib_station_daily`

#### Trafic routier

- `stg_road_traffic`
- `dim_road_arcs`
- `fct_road_traffic`
- `fct_road_traffic_current_status`
- `agg_road_traffic_daily`

#### Monitoring

- `fct_ingestion_runs`
- `fct_traffic_ingestion_runs`
- `fct_pipeline_runs`

## Dashboards Superset

Les exports versionnés sont stockés dans :

```text
superset/exports
```

### Monitoring de la plateforme

Affiche notamment :

- le taux de succès ;
- le nombre d’exécutions ;
- la durée moyenne ;
- les volumes reçus, insérés et inchangés ;
- l’évolution des durées ;
- les dernières exécutions.

### Disponibilité Vélib

Affiche notamment :

- les stations observées ;
- les vélos disponibles ;
- les bornes disponibles ;
- les stations vides ;
- la répartition par statut ;
- une carte interactive des stations ;
- l’évolution quotidienne des vélos disponibles.

### Trafic routier parisien

Affiche notamment :

- les arcs routiers observés ;
- le débit moyen ;
- le taux d’occupation moyen ;
- les arcs congestionnés ;
- la répartition par état ;
- une carte interactive du trafic ;
- l’évolution quotidienne du débit.

## Prérequis

- Git
- Docker Desktop ou Docker Engine
- Docker Compose v2
- au moins 8 Go de mémoire disponible pour Docker
- Python 3.11 pour les tests locaux

## Installation locale

### 1. Cloner le dépôt

```bash
git clone \
  https://github.com/Adjanouhoun/data-pipeline-mobility.git

cd data-pipeline-mobility
```

### 2. Créer la configuration locale

```bash
cp .env.example .env
```

Remplacer toutes les valeurs `replace_with_...` par des secrets robustes.

Sur macOS ou Linux, renseigner l’identifiant de l’utilisateur courant :

```bash
id -u
```

Reporter cette valeur dans :

```dotenv
AIRFLOW_UID=501
```

La valeur `501` est un exemple courant sur macOS. Utiliser la valeur réellement retournée par `id -u`.

Générer une clé Superset robuste avec :

```bash
openssl rand -base64 48
```

Ne jamais versionner `.env`.

### 3. Valider la configuration

```bash
docker compose config --quiet
```

Une commande sans sortie indique que la configuration est valide.

### 4. Construire l’image Airflow/dbt

```bash
docker compose build airflow-init
```

### 5. Initialiser Airflow

```bash
docker compose up airflow-init
```

Le conteneur doit terminer avec un code de sortie `0`.

### 6. Démarrer la plateforme

```bash
docker compose up -d
```

Vérifier l’état des services :

```bash
docker compose ps
```

### 7. Initialiser Superset

```bash
docker compose exec superset superset db upgrade
docker compose exec superset superset fab create-admin
docker compose exec superset superset init
```

La commande `create-admin` demande les informations du compte administrateur.

### 8. Configurer l’entrepôt dans Superset

Dans Superset, ajouter une connexion nommée :

```text
Mobility Warehouse
```

URI :

```text
postgresql+psycopg2://WAREHOUSE_USER:WAREHOUSE_PASSWORD@postgres_destination:5432/WAREHOUSE_DATABASE
```

Remplacer les valeurs par celles de `.env`.

Les exports versionnés contiennent uniquement un mot de passe masqué par `XXXXXXXXXX`.

## Interfaces locales

| Service | Adresse |
|---|---|
| Airflow | http://localhost:8085 |
| Superset | http://localhost:8088 |
| pgAdmin | http://localhost:8051 |
| PostgreSQL Warehouse | localhost:5435 |

## Environnement Python local

Créer l’environnement :

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

Installer les dépendances de développement :

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## Tests Python

```bash
PYTHONPYCACHEPREFIX=/tmp/mobility-pycache \
python -m unittest discover \
  -s tests/unit \
  -p "test_*.py" \
  -v
```

## Validation des DAG Airflow

```bash
docker compose run --rm airflow-scheduler \
  airflow dags list-import-errors
```

Résultat attendu :

```text
No data found
```

Lister les DAG :

```bash
docker compose run --rm airflow-scheduler \
  airflow dags list
```

## Commandes dbt

### Vérifier la connexion

```bash
docker compose run --rm airflow-scheduler bash -c \
  'cd /opt/airflow/dbt_mobility && \
  dbt debug --profiles-dir .'
```

### Construire tous les modèles

```bash
docker compose run --rm airflow-scheduler bash -c \
  'cd /opt/airflow/dbt_mobility && \
  dbt run --profiles-dir .'
```

### Exécuter les tests

```bash
docker compose run --rm airflow-scheduler bash -c \
  'cd /opt/airflow/dbt_mobility && \
  dbt test --profiles-dir .'
```

Le test `assert_bikes_available_under_total_capacity` est configuré en avertissement, car l’API peut ponctuellement déclarer davantage de vélos que la capacité annoncée.

### Contrôler la fraîcheur

```bash
docker compose run --rm airflow-scheduler bash -c \
  'cd /opt/airflow/dbt_mobility && \
  dbt source freshness --profiles-dir .'
```

Une source peut être marquée périmée lorsque l’API amont ne publie pas de nouvelle donnée, même si le pipeline fonctionne correctement.

## Tester les DAG complets

### Vélib

```bash
docker compose run --rm airflow-scheduler \
  airflow dags test \
  ingest_and_transform_velib \
  2026-07-18T18:00:00+00:00
```

### Trafic routier

```bash
docker compose run --rm airflow-scheduler \
  airflow dags test \
  ingest_paris_road_traffic \
  2026-07-18T18:35:00+00:00
```

Pour de nouveaux tests, utiliser une date logique unique et cohérente avec l’environnement.

## Sauvegarde PostgreSQL

Créer une sauvegarde :

```bash
./scripts/backup_warehouse.sh
```

Les archives sont créées dans :

```text
backups/postgresql
```

Le dossier `backups/` est ignoré par Git.

## Vérification d’une sauvegarde

```bash
./scripts/verify_warehouse_backup.sh \
  backups/postgresql/mobility_warehouse_TIMESTAMP.dump
```

La vérification :

1. contrôle la somme SHA-256 ;
2. inspecte la structure de l’archive ;
3. crée une base temporaire ;
4. restaure la sauvegarde ;
5. vérifie les relations attendues ;
6. compare les volumes restaurés ;
7. crée un marqueur `.verified` ;
8. supprime la base temporaire.

## Politique de rétention

Afficher les lignes candidates sans rien supprimer :

```bash
./scripts/apply_data_retention.sh
```

L’exécution réelle exige :

- une sauvegarde vérifiée ;
- son fichier `.verified` ;
- une confirmation explicite.

```bash
RETENTION_CONFIRMATION=DELETE_EXPIRED_MOBILITY_DATA \
./scripts/apply_data_retention.sh \
  --execute \
  --verified-backup \
  backups/postgresql/mobility_warehouse_TIMESTAMP.dump
```

Politiques par défaut :

- détail RAW Vélib : 30 jours ;
- détail analytique Vélib : 24 mois ;
- détail RAW trafic : 7 jours ;
- détail analytique trafic : 6 mois ;
- monitoring : 12 mois ;
- agrégats quotidiens : conservés.

## Protection des modèles historiques

Les reconstructions complètes des modèles historiques protégés sont bloquées par défaut.

Une reconstruction destructive nécessite :

```bash
dbt run \
  --full-refresh \
  --vars '{"allow_destructive_full_refresh": true}'
```

Cette option ne doit être utilisée qu’après une sauvegarde vérifiée et une approbation explicite.

## Structure du projet

```text
.
├── dags/                     DAG Airflow et bibliothèques d’ingestion
├── dbt_mobility/             Projet dbt
├── docs/sprints/             Documentation détaillée des sprints
├── scripts/                  Sauvegarde, restauration et rétention
├── sql/                      Migrations PostgreSQL
├── superset/exports/         Dashboards Superset versionnés
├── tests/unit/               Tests unitaires Python
├── Dockerfile.airflow        Image Airflow avec dbt et Git
├── docker-compose.yml        Services locaux
├── requirements-airflow.txt  Dépendances de l’image Airflow
├── requirements-dev.txt      Dépendances de développement
└── superset_config.py        Configuration Superset
```

## Sécurité

- les secrets sont externalisés dans `.env` ;
- `.env` est ignoré par Git ;
- les exports Superset masquent les mots de passe ;
- les migrations SQL sont montées en lecture seule dans Airflow ;
- les suppressions de rétention nécessitent une sauvegarde vérifiée ;
- les reconstructions dbt destructives sont protégées ;
- les opérations DML sont désactivées dans la connexion Superset exportée.

Les infobulles personnalisées des cartes nécessitent :

```text
ENABLE_JAVASCRIPT_CONTROLS
```

et l’autorisation CSP :

```text
unsafe-eval
```

Cette autorisation réduit la protection du navigateur. Les droits de modification des graphiques doivent être réservés aux administrateurs de confiance.

## Documentation détaillée

Les décisions, validations et résultats de chaque étape sont disponibles dans :

```text
docs/sprints/sprint-01.md
...
docs/sprints/sprint-13.md
```

## État du projet

La plateforme locale comprend :

- deux pipelines Airflow fonctionnels ;
- un entrepôt PostgreSQL historisé ;
- des modèles dbt incrémentaux ;
- des contrôles de qualité ;
- des métriques d’observabilité ;
- trois dashboards Superset ;
- une procédure de sauvegarde et de restauration ;
- une politique de rétention protégée.

Le prochain objectif est le déploiement sur une VM OVH.
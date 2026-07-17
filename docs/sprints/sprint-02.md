# Sprint 2 — Image Airflow et exécution dbt reproductible

## Objectif

Installer dbt une seule fois lors de la construction de l’image Airflow,
au lieu de le télécharger pendant chaque exécution du DAG.

## Image personnalisée

L’image est construite à partir de :

```text
apache/airflow:2.9.1-python3.11
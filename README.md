# llmapps
llm apps 

# Setup
## alembic Setup
run
```
mkdir alembic
alembic init alembic
```
update target_metadata in alembic/env.py

## Environment Setup
update the environment variables in .env
update `sqlalchemy.url` in alembic.ini
if the postgres is setup for the first time in the environment, run
```
alembic revision --autogenerate -m "Initial migration"
```
then for each db schema update, run
```
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```
Copy gmail_token.json to related folder and update APP_MANAGER_GMAIL_CREDS_PATH environment pointing to it. 
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
If a new schema model file is added under backend/db/models, expose it in __init__.py. Otherwise, it can't be added to db by the above upgrade scripts. 


Copy gmail_creds.json and backend/token.json to related folder and update APP_MANAGER_GMAIL_CREDS_PATH environment pointing to it for gmail api access. 

*pgvector*
https://dev.to/farez/installing-postgresql-pgvector-on-debian-fcf 
https://github.com/pgvector/pgvector
```
psql --version #get version number
sudo apt install postgresql-{version}-pgvector
#Login to PostgreSQL
psql -U db-username db-name
#Enable pgvector
CREATE EXTENSION vector;
#Check that it's enabled
\dx
```

# Design
## Tech Stack
- **Frontend: NextJs + tailwind css** 
  - Though, NextJs offers server components, I decide to force it to treat components as client components only as much as possible. Because complex client side state interaction across multiple components can't be achieved by server component. Server component is useful only when 2 pages are completely independent. Within the same page, it should only use client component.
- **Backend: Python FastAPI framework** 
  - Seem to be a lightweight popular api framework. Also python is preferred language for AI application logic. NextJs can act as frontend server which calls python server for data. 
- **Database: Postgres & Redis**
  - Redis is used to manage session and support rate limiting. 
  - PostgreSQL is a popular relational database which also supports vector search feature. In llm apps, I want to persist user preference with some additional metadata like date, food category and filter by them. So a relational db with vector search capability satisfies the requirements.

# Implementation Details
## Database management
- sqlalchemy is python ORM for PostgreSQL.
- alembic is schema version management system used together with sqlalchemy. 

## NextJs Middleware
- Used to check session validity and redirect based on session state. It has to be put in project root folder rather than frontend code root folder so that it can be picked up by NextJs server. 
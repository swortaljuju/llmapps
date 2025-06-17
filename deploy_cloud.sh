conda activate llmapps
git fetch origin
git rebase origin/main
npm install
conda env update --file environment.yml --prune
alembic upgrade head
npm run build
# supervisorctl update if you have changed the config files
sudo supervisorctl restart llmapps:*

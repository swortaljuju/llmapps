systemctl start postgresql.service
systemctl enable redis-server
systemctl start redis-server
alembic upgrade head
npm run dev
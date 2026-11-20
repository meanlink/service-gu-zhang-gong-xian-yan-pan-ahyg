from sqlalchemy import inspect, text
from src.config.database import Base, engine
from src import models
def migrate():
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        columns = [c['name'] for c in inspect(conn).get_columns('jobs')]
        if 'invalidated' not in columns:
            conn.execute(text('ALTER TABLE jobs ADD COLUMN invalidated BOOLEAN NOT NULL DEFAULT FALSE'))
if __name__=='__main__':migrate()

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from flask_migrate import Migrate

migrate = Migrate(app, db)

def upgrade():
    # Use SQLAlchemy ORM to safely modify the table
    with app.app_context():
        if 'image_url' in db.Model.metadata.tables['article'].columns:
            db.Model.metadata.tables['article'].columns.pop('image_url')
            db.session.commit()

def downgrade():
    # Add back the image_url column if needed
    with app.app_context():
        if 'image_url' not in db.Model.metadata.tables['article'].columns:
            db.Model.metadata.tables['article'].columns['image_url'] = db.Column(db.String(500))
            db.session.commit()

if __name__ == '__main__':
    upgrade()

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app, db
from models import User

def create_admin_user():
    with app.app_context():
        try:
            # Check if admin already exists
            admin = User.query.filter_by(email='admin@example.com').first()
            if admin:
                print("Admin user already exists!")
                return
            
            # Create admin user
            admin = User(
                username='admin',
                email='admin@example.com',
                is_admin=True
            )
            admin.set_password('admin123')
            
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")
        except Exception as e:
            print(f"Error creating admin user: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    create_admin_user()

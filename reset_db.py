from app import app, db

with app.app_context():
    print("Dropping all tables...")
    db.drop_all()
    print("Creating all tables...")
    db.create_all()
    from app import _seed_data
    print("Seeding new data...")
    _seed_data()
    print("Database reset complete.")

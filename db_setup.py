from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    sites = db.relationship('Site', backref='user', lazy=True)


class Site(db.Model):
    __tablename__ = "sites"
    id = db.Column(db.Integer, primary_key=True)
    site_unit = db.Column(db.String(100))
    compound = db.Column(db.String(50))
    aquifer_thickness = db.Column(db.Float)
    plume_length = db.Column(db.Float)
    plume_width = db.Column(db.Float)
    hydraulic_conductivity = db.Column(db.Float)
    electron_donor = db.Column(db.Float)
    electron_acceptor_o2 = db.Column(db.Float)
    electron_acceptor_no3 = db.Column(db.Float)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

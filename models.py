#Import the object that would help in database creation
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

#initialize SQLAlchemy
db= SQLAlchemy()

#Creating the database models
#user table
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    fullname = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)
    dob = db.Column(db.Date, nullable=True)
    state = db.Column(db.String(50), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    reservations = db.relationship('Reservation', backref='user', lazy=True)


#parking lot table
class ParkingLot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prime_location_name = db.Column(db.String(150), nullable=False)
    price_per_hour = db.Column(db.Float, nullable=False)
    address = db.Column(db.String(200), nullable=False)
    pin_code = db.Column(db.String(12), nullable=False)
    max_spots = db.Column(db.Integer, nullable=False)
    spots = db.relationship('ParkingSpot', backref='lot', lazy=True)


#parking spot table
class ParkingSpot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign key to ParkingLot
    lot_id = db.Column(db.Integer, db.ForeignKey('parking_lot.id'), nullable=False)
    
    status = db.Column(db.String(1), default='A')  # A = Available, O = Occupied
    spot_number = db.Column(db.String(10), nullable=False)

    # One-to-One: A spot can have one reservation at a time
    reservation = db.relationship('Reservation', backref='spot', uselist=False)
    
#reservation parking lot table
class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    # Foreign key to ParkingSpot
    spot_id = db.Column(db.Integer, db.ForeignKey('parking_spot.id'), nullable=False)

    # Foreign key to User
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    parking_timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    leaving_timestamp = db.Column(db.DateTime, nullable=True)

    cost_per_hour = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Pending')

    # Method to compute total bill after leaving
    def calculate_total_cost(self):
        if self.leaving_timestamp:
            duration = (self.leaving_timestamp - self.parking_timestamp).total_seconds() / 3600
            self.total_cost = round(duration * self.cost_per_hour, 2)
            return self.total_cost
        return 0.0
#A decent amount of normlization has been done

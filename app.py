import os
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from models import db, User, ParkingLot, ParkingSpot, Reservation

app = Flask(__name__, instance_relative_config=True)#relative config allows Flask to find the instance folder

# Loading environment variables
from dotenv import load_dotenv
load_dotenv()

# App configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', '1234567890')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///parking_management.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Creating the database tables
with app.app_context():
    db.create_all()

#home route

@app.route('/')
def index():
    return jsonify({'message': 'Welcome to the Parking Reservation Interface!!'})

#users route

@app.route('/users', methods=['POST'])
def register_user():
    payload = request.get_json()
    new_user = User(
        username=payload['username'],
        password=payload['password'],
        is_admin=payload.get('is_admin', False)
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User account created', 'user_id': new_user.id}), 201

@app.route('/users', methods=['GET'])
def fetch_all_users():
    user_list = User.query.all()
    results = [{
        'id': u.id,
        'username': u.username,
        'is_admin': u.is_admin
    } for u in user_list]
    return jsonify(results)

@app.route('/users/<int:user_id>', methods=['GET'])
def fetch_user_by_id(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'is_admin': user.is_admin
    })

@app.route('/users/<int:user_id>', methods=['DELETE'])
def remove_user(user_id):
    target = User.query.get_or_404(user_id)
    db.session.delete(target)
    db.session.commit()
    return jsonify({'message': f'User {user_id} has been deleted.'})

#parking lot route

@app.route('/lots', methods=['POST'])
def add_parking_lot():
    payload = request.get_json()
    lot = ParkingLot(
        prime_location_name=payload['prime_location_name'],
        price_per_hour=payload['price_per_hour'],
        address=payload['address'],
        pin_code=payload['pin_code'],
        max_spots=payload['max_spots']
    )
    db.session.add(lot)
    db.session.commit()
    return jsonify({'message': 'Congratulations!!! Parking lot added successfully', 'lot_id': lot.id}), 201

@app.route('/lots', methods=['GET'])
def list_all_lots():
    lots = ParkingLot.query.all()
    return jsonify([
        {
            'id': l.id,
            'location_name': l.prime_location_name,
            'rate': l.price_per_hour,
            'address': l.address,
            'pincode': l.pin_code,
            'total_spots': l.max_spots
        } for l in lots
    ])

#reservation route
@app.route('/reservations', methods=['POST'])
def book_spot():
    data = request.get_json()
    selected_spot = ParkingSpot.query.get_or_404(data['spot_id'])

    if selected_spot.status == 'O':
        return jsonify({'error': 'Sorry, this spot is currently occupied. Please select another spot or come back later.'}), 409

    reservation = Reservation(
        spot_id=selected_spot.id,
        user_id=data['user_id'],
        cost_per_hour=data['cost_per_hour']
    )

    selected_spot.status = 'O'
    db.session.add(reservation)
    db.session.commit()

    return jsonify({
        'message': 'Thank You! Your reservation has been created successfully.',
        'reservation_id': reservation.id
    }), 201

@app.route('/reservations/<int:res_id>/leave', methods=['POST'])
def finish_parking(res_id):
    reservation = Reservation.query.get_or_404(res_id)

    if reservation.leaving_timestamp is not None:
        return jsonify({'error': 'Oops! This reservation has already ended.'}), 400

    reservation.leaving_timestamp = datetime.utcnow()
    reservation.calculate_total_cost()
    reservation.spot.status = 'A'

    db.session.commit()

    return jsonify({
        'message': 'Checkout complete.',
        'final_cost': reservation.total_cost
    })

@app.route('/reservations', methods=['GET'])
def show_reservations():
    all_reservations = Reservation.query.all()
    return jsonify([
        {
            'id': r.id,
            'user': r.user.username,
            'spot_number': r.spot.spot_number,
            'start_time': r.parking_timestamp.isoformat(),
            'end_time': r.leaving_timestamp.isoformat() if r.leaving_timestamp else None,
            'total_cost': r.total_cost
        } for r in all_reservations
    ])

if __name__ == '__main__':
    app.run(debug=True)

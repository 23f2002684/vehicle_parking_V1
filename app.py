import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from models import db, User, ParkingLot, ParkingSpot, Reservation
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

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
def get_lot_by_id(lot_id):
    return ParkingLot.query.get_or_404(lot_id)

def count_occupied_spots(lot_id):
    return ParkingSpot.query.filter_by(lot_id=lot_id, status='O').count()

def get_available_spot(lot_id):
    return ParkingSpot.query.filter_by(lot_id=lot_id, status='A').first()

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first', 'danger')
            return redirect(url_for('user_login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            flash('Admin access required', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

#home route
@app.route('/')
def home():
    return render_template('index.html')

#users route
@app.route('/register_user', methods=['GET', 'POST'])
def register_user():
        if request.method == 'POST':
            fullname = request.form['fullname']
            username = request.form['username']
            email = request.form['email']
            password = generate_password_hash(request.form['password'])
            dob = datetime.strptime(request.form['dob'], '%Y-%m-%d').date()
            state = request.form['State']
            
            if User.query.filter_by(username=username).first():
                flash('Username already taken.', 'danger')
                return redirect(url_for('register_user'))
            if User.query.filter_by(email=email).first():
                flash('Email already registered.', 'danger')
                return redirect(url_for('register_user'))

            new_user = User(
                username=username,
                fullname=fullname,
                email=email,
                password=password,
                dob=dob,
                state=state,
                is_admin=False  # Default to non-admin
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Registration successful!', 'success')
            return redirect(url_for('user_login'))
        return render_template('register_user.html')

@app.route('/user_login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            if user.is_banned:
                flash('Your account has been suspended', 'danger')
                return redirect(url_for('user_login'))
            session['user_id'] = user.id
            return redirect(url_for('user_dashboard'))
        flash('Invalid credentials', 'danger')
    return render_template('user_login.html')

# Admin routes
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username == 'admin' and password == 'unique1234':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid admin credentials', 'danger')
    return render_template('admin_login.html')
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('home'))
#dashboard routes
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    user = User.query.get(session['user_id'])
    active_reservations = Reservation.query.filter_by(
        user_id=user.id, 
        leaving_timestamp=None
    ).order_by(Reservation.parking_timestamp.desc()).limit(3).all()
    
    return render_template('user_dashboard.html', 
                          user=user, 
                          active_reservations=active_reservations)
@app.route('/admin_dashboard')
@admin_required
def admin_dashboard():
    lots=ParkingLot.query.all()
    total_users = User.query.count()
    total_lots = ParkingLot.query.count()
    active_reservations = Reservation.query.filter_by(leaving_timestamp=None).count()
    
    return render_template('admin_dashboard.html',
                          total_users=total_users,
                          total_lots=total_lots,
                          active_reservations=active_reservations,
                          lots=lots
                          )

#managing the parking lot
@app.route('/create_lot', methods=['GET', 'POST'])
@admin_required
def create_lot():
    if request.method == 'POST':
        new_lot = ParkingLot(
            prime_location_name=request.form['prime_location_name'],
            price_per_hour=float(request.form['price_per_hour']),
            address=request.form['address'],
            pin_code=request.form['pin_code'],
            max_spots=int(request.form['max_spots'])
        )
        db.session.add(new_lot)
        db.session.commit()
        for i in range(1, new_lot.max_spots + 1):
            spot = ParkingSpot(
                lot_id=new_lot.id,
                spot_number=f"{new_lot.prime_location_name[:3]}-{i:03d}",
                status='A'
            )
            db.session.add(spot)
        db.session.commit()
        flash('Parking lot created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('create_lot.html')

@app.route('/manage_lots')
@admin_required
def manage_lots():
    lots = ParkingLot.query.all()
    return render_template('manage_lots.html', lots=lots)

@app.route('/edit_lot/<int:lot_id>', methods=['GET', 'POST'])
@admin_required
def edit_lot(lot_id):
    lot = ParkingLot.query.get_or_404(lot_id)
    occupied_spots = count_occupied_spots(lot_id)
    
    if request.method == 'POST':
        lot.prime_location_name = request.form['prime_location_name']
        lot.price_per_hour = float(request.form['price_per_hour'])
        lot.address = request.form['address']
        lot.pin_code = request.form['pin_code']
        new_max = int(request.form['max_spots'])
        if new_max < occupied_spots:
            flash(f'Cannot reduce spots below {occupied_spots} occupied spots', 'danger')
            return redirect(url_for('edit_lot', lot_id=lot_id))
        if new_max > lot.max_spots:
            for i in range(lot.max_spots + 1, new_max + 1):
                spot = ParkingSpot(
                    lot_id=lot.id,
                    spot_number=f"{lot.prime_location_name[:3]}-{i:03d}",
                    status='A'
                )
                db.session.add(spot)
        elif new_max < lot.max_spots:
            # Remove available spots only
            spots_to_remove = ParkingSpot.query.filter_by(
                lot_id=lot.id, 
                status='A'
            ).limit(lot.max_spots - new_max).all()
            
            for spot in spots_to_remove:
                db.session.delete(spot)
        lot.max_spots = new_max
        db.session.commit()
        flash('Lot updated successfully', 'success')
        return redirect(url_for('manage_lots'))
    
    return render_template('edit_lot.html', lot=lot, occupied_spots=occupied_spots)

@app.route('/delete_lot/<int:lot_id>', methods=['GET', 'POST'])
@admin_required
def delete_lot(lot_id):
    lot = get_lot_by_id(lot_id)
    occupied_spots = count_occupied_spots(lot_id)
    
    if request.method == 'POST':
        if occupied_spots == 0:
            spot_ids = [spot.id for spot in ParkingSpot.query.filter_by(lot_id=lot.id).all()]
            if spot_ids:
                Reservation.query.filter(Reservation.spot_id.in_(spot_ids)).delete(synchronize_session=False)
                ParkingSpot.query.filter_by(lot_id=lot.id).delete()
            db.session.delete(lot)
            db.session.commit()
            flash('Lot deleted successfully', 'success')
            return redirect(url_for('manage_lots'))
        flash('Cannot delete lot with occupied spots', 'danger')
    
    return render_template('delete_lot.html', lot=lot, occupied_spots=occupied_spots)

# Booking system
@app.route('/user_bookings')
@login_required
def user_bookings():
    user = User.query.get(session['user_id'])
    reservations = Reservation.query.filter_by(user_id=user.id).order_by(
        Reservation.parking_timestamp.desc()
    ).all()
    return render_template('user_bookings.html', reservations=reservations)

@app.route('/booking_process', methods=['GET', 'POST'])
@login_required
def booking_process():
    if request.method == 'POST':
        # Get form data
        lot_id = request.form['location']
        parking_timestamp = datetime.strptime(request.form['parking_timestamp'], '%H:%M')
        leaving_timestamp = datetime.strptime(request.form['leaving_timestamp'], '%H:%M')

        # Get available spot
        spot = get_available_spot(lot_id)
        if not spot:
            flash('No available spots at this location', 'danger')
            return redirect(url_for('booking_process'))
        
        # Create reservation
        new_reservation = Reservation(
            spot_id=spot.id,
            user_id=session['user_id'],
            parking_timestamp=parking_timestamp,
            leaving_timestamp=leaving_timestamp,
            cost_per_hour=spot.lot.price_per_hour
        )
        spot.status = 'O'  # Mark spot as occupied
        db.session.add(new_reservation)
        db.session.commit()
        
        return redirect(url_for('book_status', booking_id=new_reservation.id))
    return render_template('booking_process.html')

# Fixed endpoint name conflict
@app.route('/book_status/<int:booking_id>')
@login_required
def book_status(booking_id):
    reservation = Reservation.query.get_or_404(booking_id)
    
    if reservation.user_id != session['user_id']:
        abort(403)
        
    return render_template('book_status.html', 
                           reservation=reservation,
                           lot=reservation.spot.lot)

@app.route('/end_reservation/<int:reservation_id>', methods=['POST'])
@login_required
def end_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
    
    # Security check
    if reservation.user_id != session['user_id']:
        abort(403)
    
    reservation.leaving_timestamp = datetime.utcnow()
    reservation.calculate_total_cost()
    reservation.spot.status = 'A'
    
    db.session.commit()
    
    flash(f'Reservation ended. Total cost: ₹{reservation.total_cost}', 'success')
    return redirect(url_for('user_bookings'))

# API endpoints
@app.route('/lots', methods=['GET'])
def get_lots():
    lots = ParkingLot.query.all()
    return jsonify([{
        'id': lot.id,
        'name': lot.prime_location_name,
        'price': lot.price_per_hour,
        'address': lot.address,
        'pincode': lot.pin_code,
        'max_spots': lot.max_spots,
        'available_spots': ParkingSpot.query.filter_by(lot_id=lot.id, status='A').count()
    } for lot in lots])

@app.route('/lot_details/<int:lot_id>')
@login_required
def lot_details(lot_id):
    lot = ParkingLot.query.get(lot_id)
    if not lot:
        return render_template('lot_details.html', lot=None, error='Lot not found')
    available_spots = ParkingSpot.query.filter_by(lot_id=lot.id, status='A').count()
    return render_template('lot_details.html', lot=lot, available_spots=available_spots)

# User profile management
@app.route('/user_profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        user.username = request.form['username']
        user.email = request.form['email']
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('user_profile'))
    
    return render_template('user_profile.html', user=user)

# Admin management routes
@app.route('/manage_users')
@admin_required
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/ban_user/<int:user_id>', methods=['POST'])
@admin_required
def ban_user(user_id):
    user = User.query.get(user_id)
    if user:
        user.is_banned = not user.is_banned
        db.session.commit()
        action = "banned" if user.is_banned else "unbanned"
        flash(f'User {action} successfully', 'success')
    return redirect(url_for('manage_users'))

@app.route('/receipts')
@admin_required
def receipts():
    reservations = Reservation.query.filter(
        Reservation.leaving_timestamp.isnot(None)
    ).order_by(Reservation.leaving_timestamp.desc()).all()
    return render_template('receipt.html', reservations=reservations)

#settings route
@app.route('/settings')
@login_required  # Optional: restrict to logged-in users
def settings():
    return render_template('settings.html')
@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        new_password = request.form['new_password']
        user.set_password(new_password)
        db.session.commit()
        flash('Password changed successfully', 'success')
        return redirect(url_for('settings'))
    return render_template('change_password.html', user=user)

#delete account route
@app.route('/delete_account', methods=['POST'])
@login_required
def delete_account():
    user = User.query.get(session['user_id'])
    if user:
        Reservation.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)
        db.session.commit()
        session.clear()
        flash("Account deleted successfully.", "info")
        return redirect(url_for('home'))
    flash("Something went wrong.", "danger")
    return redirect(url_for('settings'))

if __name__ == '__main__':
    app.run(debug=True)

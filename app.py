import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from models import Vehicle, db, User, ParkingLot, ParkingSpot, Reservation
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

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
            flash('Admin access is required', 'danger')
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
                flash('Your account has been suspended! Please contact office for more information.', 'danger')
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
        flash('Invalid admin credentials...', 'danger')
    return render_template('admin_login.html')

#dashboard routes
@app.route('/user_dashboard')
@login_required
def user_dashboard():
    user = User.query.get(session['user_id'])
    reservations = Reservation.query.filter_by(user_id=user.id).order_by(Reservation.parking_timestamp.desc()).all()
    # Bookings per lot (for pie/bar chart)
    lots_count = {}
    for i in reservations:
        lot_name = i.spot.lot.prime_location_name
        lots_count[lot_name] = lots_count.get(lot_name, 0) + 1
    user_lot_names = list(lots_count.keys())
    user_bookings_counts = list(lots_count.values())
    # Parking cost over time (for line chart, by month)
    monthly_cost = {}
    for i in reservations:
        if i.leaving_timestamp:
            month = i.leaving_timestamp.strftime('%b-%Y')
            monthly_cost[month] = monthly_cost.get(month, 0) + (i.total_cost or 0)
    user_months = sorted(monthly_cost.keys())
    user_costs = [monthly_cost[month] for month in user_months]
    active_reservations = [i for i in reservations if i.leaving_timestamp is None][:3]
    return render_template('user_dashboard.html',user_lot_names=user_lot_names,user_bookings_counts=user_bookings_counts,user_months=user_months,user_costs=user_costs,user=user,active_reservations=active_reservations)

@app.route('/admin_dashboard', methods=['GET', 'POST'])
@admin_required
def admin_dashboard():
    lots=ParkingLot.query.all()
    spots=ParkingSpot.query.order_by(ParkingSpot.spot_number).all()
    total_users = User.query.count()
    total_lots = ParkingLot.query.count()
    selected_spot = None
    reservation = None
    vehicle = None
    if request.method=='POST':
        spot_id=int(request.form['spot_id'])
        selected_spot = ParkingSpot.query.get(spot_id)
        reservation=Reservation.query.filter_by(
            spot_id=spot_id, 
            status="Confirmed", 
            leaving_timestamp=None
        ).order_by(Reservation.parking_timestamp.desc()).first()
        if selected_spot:
            last_reservation = Reservation.query.filter_by(
                spot_id=selected_spot.id
            ).order_by(Reservation.parking_timestamp.desc()).first()
            vehicle = last_reservation.vehicle if last_reservation else None
            reservation = last_reservation if selected_spot.status == 'O' else None
        if reservation:
            vehicle = reservation.vehicle
    return render_template('admin_dashboard.html',spots=spots,selected_spot=selected_spot,total_users=total_users,total_lots=total_lots,reservation=reservation,lots=lots,vehicle=vehicle)

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
    # Prepare chart data
    admin_lot_names = []
    admin_max_spots = []
    admin_occupied = []
    admin_available = []
    for lot in lots:
        spots = lot.spots
        total = lot.max_spots
        occupied = sum(1 for spot in spots if spot.status == 'O')
        available = total - occupied
        admin_lot_names.append(lot.prime_location_name)
        admin_max_spots.append(total)
        admin_occupied.append(occupied)
        admin_available.append(available)
    return render_template('manage_lots.html', lots=lots,admin_lot_names=admin_lot_names,admin_max_spots=admin_max_spots,admin_occupied=admin_occupied,admin_available=admin_available)

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
            flash(f'Can\'t reduce spots below {occupied_spots} occupied spots', 'danger')
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
        flash('Lot Update Success!', 'success')
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
            flash('Lot deleted successfully!', 'success')
            return redirect(url_for('manage_lots'))
        flash('Can\'t delete lot with occupied spots', 'danger')
    return render_template('delete_lot.html', lot=lot, occupied_spots=occupied_spots)

# Booking system
@app.route('/user_bookings')
@login_required
def user_bookings():
    user = User.query.get(session['user_id'])
    reservations = Reservation.query.filter_by(user_id=session['user_id']).all()
    lot_counts = {}
    for r in reservations:
        lot_name = r.spot.lot.prime_location_name
        lot_counts[lot_name] = lot_counts.get(lot_name, 0) + 1
    user_lot_names = list(lot_counts.keys())
    user_bookings_counts = list(lot_counts.values())
    cost_by_month = {}
    for r in reservations:
        if r.leaving_timestamp:
            month = r.parking_timestamp.strftime('%b-%Y')
            cost_by_month[month] = cost_by_month.get(month, 0) + (r.total_cost or 0)
    user_months = sorted(cost_by_month.keys())
    user_costs = [cost_by_month[month] for month in user_months]
    return render_template('user_bookings.html', reservations=reservations, now=datetime.utcnow(), user=user, lot_counts=lot_counts, user_lot_names=user_lot_names,user_bookings_counts=user_bookings_counts, user_months=user_months, user_costs=user_costs)

@app.route('/booking_process', methods=['GET', 'POST'])
@login_required
def booking_process():
    if request.method == 'POST':
        lot_id = request.form['location']
        parking_timestamp = datetime.strptime(request.form['parking_timestamp'], '%Y-%m-%dT%H:%M')
        leaving_timestamp = datetime.strptime(request.form['leaving_timestamp'], '%Y-%m-%dT%H:%M')
        vehicle_brand = request.form['vehicle_brand']
        vehicle_model = request.form['vehicle_model']
        vehicle_class = request.form['vehicle_class']
        vehicle_reg_no = request.form['vehicle_reg_no']
        spot = get_available_spot(lot_id)
        # Create reservation
        if spot:
            vehicle = Vehicle.query.filter_by(registration_number=vehicle_reg_no).first()
            if not vehicle:
                vehicle = Vehicle(brand=vehicle_brand,model_name=vehicle_model,vehicle_class=vehicle_class,vehicle_type='4-wheeler', registration_number=vehicle_reg_no)
            db.session.add(vehicle)
            db.session.commit() 
            new_reservation = Reservation(spot_id=spot.id,user_id=session['user_id'],parking_timestamp=parking_timestamp,leaving_timestamp=leaving_timestamp,cost_per_hour=spot.lot.price_per_hour,vehicle_id=vehicle.id,status="Confirmed")
            new_reservation.calculate_total_cost()
            spot.status = 'O'  
            db.session.add(new_reservation)
            db.session.commit()
            flash('Booking successful!', 'success')
            return redirect(url_for('book_status', booking_id=new_reservation.id))
        else:
            flash('No available spots at this location. How about another location?', 'danger')
            return redirect(url_for('booking_process'))
    return render_template('booking_process.html')

@app.route('/book_status/<int:booking_id>')
@login_required
def book_status(booking_id):
    reservation = Reservation.query.get_or_404(booking_id)
    if reservation.user_id != session['user_id']:
        abort(403)    
    return render_template('book_status.html', reservation=reservation,lot=reservation.spot.lot, now=datetime.utcnow())
    
@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    booking = Reservation.query.get_or_404(booking_id)
    if booking.user_id != session['user_id']:
        abort(403)
    if booking.status not in ["Completed", "Cancelled", "Rejected"]:
        booking.status = "Cancelled"
        if booking.spot.status == 'O':
            booking.spot.status = 'A'
        db.session.commit()
        flash('Booking is cancelled!', 'warning')
    return redirect(url_for('user_bookings'))

@app.route('/end_reservation/<int:reservation_id>', methods=['POST'])
@login_required
def end_reservation(reservation_id):
    reservation = Reservation.query.get_or_404(reservation_id)
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
    return jsonify([{'id': lot.id,'name': lot.prime_location_name,'price': lot.price_per_hour,'address': lot.address,'pincode': lot.pin_code,'max_spots': lot.max_spots,'available_spots': ParkingSpot.query.filter_by(lot_id=lot.id, status='A').count()} for lot in lots])

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
    reservations= Reservation.query.filter_by(user_id=user.id).all()
    if request.method == 'POST':
        user.username = request.form['username']
        user.email = request.form['email']
        user.fullname = request.form['full-name']
        db.session.commit()
        return redirect(url_for('user_profile'))
    return render_template('user_profile.html', user=user, reservations=reservations)

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    user = User.query.get(session['user_id'])
    user.username = request.form['username']
    user.email = request.form['email']
    user.fullname = request.form['full-name']
    db.session.commit()
    flash('Profile Update Success!', 'success')
    return redirect(url_for('user_profile'))

# Admin work routes
@app.route('/manage_users')
@admin_required
def manage_users():
    users = User.query.all()
    lots = ParkingLot.query.all()
    return render_template('manage_users.html', users=users, lots=lots)
    
@app.route('/ban_user/<int:user_id>', methods=['POST'])
@admin_required
def ban_user(user_id):
    user = User.query.get_or_404(user_id)
    if user:
        user.is_banned = not user.is_banned
        db.session.commit()
        action = "banned" if user.is_banned else "unbanned"
        flash(f'User {action} successfully', 'success')
    return redirect(url_for('manage_users'))

@app.route('/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()
    if 'is_banned' in data:
        user.is_banned = bool(data['is_banned'])
        db.session.commit()
        return {'success': True, 'is_banned': user.is_banned}, 200
    return {'error': 'Invalid request'}, 400

#receipt generation
@app.route('/receipts')
@admin_required
def receipts():
    reservations = Reservation.query.filter(
        Reservation.leaving_timestamp.isnot(None), Reservation.status!="Cancelled"
    ).order_by(Reservation.leaving_timestamp.desc()).all()
    receipts = []
    for i in reservations:
        receipts.append({'id': i.id,'username': i.user.username,'fullname': i.user.fullname,'parking_spot': i.spot.spot_number,'booking_date': i.parking_timestamp.strftime('%d-%m-%Y'),'start_time': i.parking_timestamp.strftime('%I:%M %p'),'hours_parked': round((i.leaving_timestamp - i.parking_timestamp).total_seconds() / 3600, 2),'rate_per_hour': i.cost_per_hour,'total_amount': i.total_cost})
    return render_template('receipt.html', receipts=receipts)

#settings route
@app.route('/settings')
@login_required  
def settings():
    user = User.query.get(session['user_id'])
    reservations= Reservation.query.filter_by(user_id=user.id).all()
    return render_template('settings.html', user=user, reservations=reservations)

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form['current_password']
    new_password = request.form['new_password']
    confirm_password = request.form['confirm_password']
    user = User.query.get(session['user_id'])
    if not check_password_hash(user.password, current_password):
        flash('Current password is incorrect!', 'danger')
        return redirect(url_for('settings'))
    if new_password != confirm_password:
        flash('Passwords don\'t match! Check again.', 'danger')
        return redirect(url_for('settings'))
    user.password = generate_password_hash(new_password)
    db.session.commit()
    flash('Password has been updated successfully!', 'success')
    return redirect(url_for('settings'))

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    flash('Oops! You have been logged out', 'info')
    return redirect(url_for('home'))

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
        flash("Account has been deleted successfully!", "info")
        return redirect(url_for('home'))
    flash("Something went wrong.", "danger")
    return redirect(url_for('settings'))

if __name__ == '__main__':
    app.run(debug=True)
